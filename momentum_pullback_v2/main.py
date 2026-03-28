import argparse
import logging
import time
from datetime import datetime, timezone

import ccxt

from momentum_pullback_v2.config import EXCHANGE_ID, INITIAL_BALANCE, LOG_PATH, SYMBOLS, TF_CONTEXT, TF_ENTRY
from momentum_pullback_v2.db import init_db, insert_trade
from momentum_pullback_v2.execution import build_trade
from momentum_pullback_v2.exit_manager import manage_exit
from momentum_pullback_v2.indicators import rsi
from momentum_pullback_v2.risk import risk_checks
from momentum_pullback_v2.scanner import scan_all_assets
from momentum_pullback_v2.state import BotState

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()])


def create_exchange():
    return getattr(ccxt, EXCHANGE_ID)({'enableRateLimit': True})


def fetch_ohlcv_safe(exchange, symbol, timeframe, limit=200, retries=5):
    delay = 1
    for attempt in range(retries):
        try:
            return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        except Exception as exc:
            if attempt == retries - 1:
                raise
            logging.warning('fetch_ohlcv retry %s %s %s: %s', symbol, timeframe, attempt + 1, exc)
            time.sleep(delay)
            delay *= 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', default=True)
    args = parser.parse_args()

    init_db()
    exchange = create_exchange()
    state = BotState(balance=INITIAL_BALANCE, daily_start_balance=INITIAL_BALANCE, session_peak_balance=INITIAL_BALANCE)
    open_trade = None

    logging.info('Momentum Pullback v2 started | dry_run=%s | exchange=%s', args.dry_run, EXCHANGE_ID)

    while True:
        ok, reason = risk_checks(state)
        if not ok:
            logging.warning('risk blocked: %s', reason)
            time.sleep(15)
            continue

        symbol_to_candles_5m = {}
        symbol_to_candles_15m = {}
        for symbol in SYMBOLS:
            try:
                symbol_to_candles_5m[symbol] = fetch_ohlcv_safe(exchange, symbol, TF_ENTRY, limit=200)
                symbol_to_candles_15m[symbol] = fetch_ohlcv_safe(exchange, symbol, TF_CONTEXT, limit=200)
            except Exception as exc:
                logging.warning('fetch failed %s: %s', symbol, exc)

        if open_trade is None:
            signal = scan_all_assets(symbol_to_candles_5m, symbol_to_candles_15m)
            if signal:
                trade = build_trade(signal, state.balance)
                if trade:
                    trade['opened_at'] = datetime.now(timezone.utc)
                    open_trade = trade
                    logging.info('OPEN %s %s entry=%s sl=%s tp=%s size=%s score=%.3f', trade['symbol'], trade['direction'], trade['entry'], trade['sl'], trade['tp'], trade['size'], trade['score'])
        else:
            candles = symbol_to_candles_5m.get(open_trade['symbol'])
            if candles:
                candle = candles[-1]
                current_price = candle[4]
                minutes_elapsed = (datetime.now(timezone.utc) - open_trade['opened_at']).total_seconds() / 60.0
                rsi_5m = rsi([c[4] for c in candles], 14)
                exit_price, exit_reason, closed = manage_exit(open_trade, current_price, candle, minutes_elapsed, rsi_5m)
                logging.info('MANAGE %s %s price=%s sl=%s tp=%s reason=%s minutes=%.2f', open_trade['symbol'], open_trade['direction'], current_price, open_trade['sl'], open_trade['tp'], exit_reason, minutes_elapsed)
                if closed:
                    gross = (exit_price - open_trade['entry']) * open_trade['size'] if open_trade['direction'] == 'LONG' else (open_trade['entry'] - exit_price) * open_trade['size']
                    fee = open_trade['fee'] + open_trade['slippage']
                    pnl = gross - fee
                    state.balance += pnl
                    state.session_peak_balance = max(state.session_peak_balance, state.balance)
                    state.trades_today += 1
                    if pnl <= 0:
                        state.consecutive_losses += 1
                    else:
                        state.consecutive_losses = 0
                    insert_trade((datetime.now(timezone.utc).isoformat(), open_trade['symbol'], open_trade['direction'], open_trade['entry'], exit_price, open_trade['size'], pnl, fee, exit_reason, state.balance))
                    logging.info('CLOSE %s %s pnl=%s fee=%s reason=%s balance=%s', open_trade['symbol'], open_trade['direction'], round(pnl, 6), round(fee, 6), exit_reason, round(state.balance, 6))
                    open_trade = None
        time.sleep(20)


if __name__ == '__main__':
    main()
