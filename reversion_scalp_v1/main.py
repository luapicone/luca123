import argparse
import logging
import time
from datetime import datetime, timezone

import ccxt

from reversion_scalp_v1.config import EXCHANGE_ID, INITIAL_BALANCE, LOG_PATH, SYMBOLS, TF_CONTEXT, TF_ENTRY, SYMBOL_COOLDOWN_MINUTES, SYMBOL_REPEAT_LOSS_COOLDOWN_MINUTES
from reversion_scalp_v1.db import init_db, insert_trade
from reversion_scalp_v1.execution import build_trade
from reversion_scalp_v1.exit_manager import manage_exit
from reversion_scalp_v1.indicators import rsi
from reversion_scalp_v1.risk import risk_checks
from reversion_scalp_v1.scanner import scan_all_assets
from reversion_scalp_v1.state import BotState

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()])


def create_exchange():
    return getattr(ccxt, EXCHANGE_ID)({'enableRateLimit': True})


def fetch_ohlcv_safe(exchange, symbol, timeframe, limit=120, retries=5):
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
    logging.info('Reversion Scalp v1 started | dry_run=%s | exchange=%s', args.dry_run, EXCHANGE_ID)
    cycle = 0

    while True:
        cycle += 1
        logging.info('scan_cycle_start cycle=%s balance=%.6f open_trade=%s', cycle, state.balance, bool(open_trade))
        ok, reason = risk_checks(state)
        if not ok:
            logging.warning('risk blocked: %s', reason)
            time.sleep(15)
            continue

        symbol_to_candles_5m = {}
        symbol_to_candles_15m = {}
        for symbol in SYMBOLS:
            try:
                logging.info('fetch_start cycle=%s symbol=%s tf=%s/%s', cycle, symbol, TF_ENTRY, TF_CONTEXT)
                symbol_to_candles_5m[symbol] = fetch_ohlcv_safe(exchange, symbol, TF_ENTRY, limit=120)
                symbol_to_candles_15m[symbol] = fetch_ohlcv_safe(exchange, symbol, TF_CONTEXT, limit=120)
                logging.info('fetch_done cycle=%s symbol=%s candles_5m=%s candles_15m=%s', cycle, symbol, len(symbol_to_candles_5m[symbol]), len(symbol_to_candles_15m[symbol]))
            except Exception as exc:
                logging.warning('fetch failed %s: %s', symbol, exc)

        if open_trade is None:
            signal, diagnostics = scan_all_assets(symbol_to_candles_5m, symbol_to_candles_15m)
            if signal:
                cooldown_key = f"{signal['symbol']}|{signal['direction']}"
                now_ts = datetime.now(timezone.utc).timestamp()
                cooldown_until = state.symbol_cooldowns.get(cooldown_key)
                if cooldown_until and now_ts < cooldown_until:
                    diagnostics[signal['symbol']] = {'rejected': 'symbol_direction_cooldown', 'direction': signal['direction']}
                    logging.info('scan_cycle_no_signal cycle=%s symbols_ready=%s diagnostics=%s', cycle, len(symbol_to_candles_5m), diagnostics)
                else:
                    trade = build_trade(signal, state.balance)
                    if trade:
                        trade['opened_at'] = datetime.now(timezone.utc)
                        open_trade = trade
                        logging.info('OPEN %s %s entry=%s sl=%s tp=%s size=%s score=%.3f stretch=%.6f zscore=%.3f', trade['symbol'], trade['direction'], trade['entry'], trade['sl'], trade['tp'], trade['size'], trade['score'], trade['stretch'], trade['zscore'])
            else:
                logging.info('scan_cycle_no_signal cycle=%s symbols_ready=%s diagnostics=%s', cycle, len(symbol_to_candles_5m), diagnostics)
        else:
            candles = symbol_to_candles_5m.get(open_trade['symbol'])
            if candles:
                candle = candles[-1]
                current_price = candle[4]
                minutes_elapsed = (datetime.now(timezone.utc) - open_trade['opened_at']).total_seconds() / 60.0
                rsi_5m = rsi([c[4] for c in candles], 14)
                exit_price, exit_reason, closed, partial = manage_exit(open_trade, current_price, candle, minutes_elapsed, rsi_5m)
                if partial:
                    partial_size, partial_realized = partial
                    logging.info('PARTIAL %s %s price=%s partial_size=%s realized=%.6f remaining_size=%s sl=%s', open_trade['symbol'], open_trade['direction'], current_price, partial_size, partial_realized, open_trade.get('remaining_size'), open_trade['sl'])
                logging.info('MANAGE %s %s price=%s sl=%s tp=%s reason=%s minutes=%.2f', open_trade['symbol'], open_trade['direction'], current_price, open_trade['sl'], open_trade['tp'], exit_reason, minutes_elapsed)
                if closed:
                    remaining_size = open_trade.get('remaining_size', open_trade['size'])
                    gross_remaining = (exit_price - open_trade['entry']) * remaining_size if open_trade['direction'] == 'LONG' else (open_trade['entry'] - exit_price) * remaining_size
                    gross = gross_remaining + open_trade.get('realized_partial_pnl', 0.0)
                    fee = open_trade['fee'] + open_trade['slippage']
                    pnl = gross - fee
                    state.balance += pnl
                    state.session_peak_balance = max(state.session_peak_balance, state.balance)
                    state.trades_today += 1
                    state.consecutive_losses = state.consecutive_losses + 1 if pnl <= 0 else 0
                    cooldown_key = f"{open_trade['symbol']}|{open_trade['direction']}"
                    cooldown_minutes = SYMBOL_REPEAT_LOSS_COOLDOWN_MINUTES if pnl <= 0 else SYMBOL_COOLDOWN_MINUTES
                    state.symbol_cooldowns[cooldown_key] = datetime.now(timezone.utc).timestamp() + (cooldown_minutes * 60)
                    insert_trade((datetime.now(timezone.utc).isoformat(), open_trade['symbol'], open_trade['direction'], open_trade['entry'], exit_price, open_trade['size'], pnl, fee, exit_reason, state.balance, open_trade.get('score'), open_trade.get('stretch'), open_trade.get('context_rsi'), open_trade.get('zscore'), minutes_elapsed, open_trade.get('mfe'), open_trade.get('mae'), open_trade.get('peak_progress')))
                    logging.info('CLOSE %s %s pnl=%s fee=%s reason=%s balance=%s mfe=%.6f mae=%.6f peak_progress=%.3f', open_trade['symbol'], open_trade['direction'], round(pnl, 6), round(fee, 6), exit_reason, round(state.balance, 6), open_trade.get('mfe', 0.0), open_trade.get('mae', 0.0), open_trade.get('peak_progress', 0.0))
                    open_trade = None
        logging.info('scan_cycle_end cycle=%s balance=%.6f open_trade=%s', cycle, state.balance, bool(open_trade))
        time.sleep(20)


if __name__ == '__main__':
    main()
