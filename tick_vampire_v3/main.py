import argparse
import logging
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import ccxt

from tick_vampire_v3.calendar import news_blackout_active
from tick_vampire_v3.config import (
    BREAKEVEN_TRIGGER_PCT,
    EARLY_FAIL_BARS,
    EXCHANGE,
    IGNORE_SESSIONS,
    INITIAL_BALANCE,
    MAX_HOLD_SECONDS,
    PRICE_WINDOW,
    RSI_PERIOD,
    SESSIONS,
    SYMBOL,
    TRAILING_GIVEBACK_PCT,
    TRAILING_TRIGGER_PCT,
    VOLUME_MA_PERIOD,
)
from tick_vampire_v3.db import init_db, insert_trade
from tick_vampire_v3.execution import execute_trade
from tick_vampire_v3.report import format_session_report
from tick_vampire_v3.risk import risk_checks
from tick_vampire_v3.signal import analyze_entry_signal, simple_rsi
from tick_vampire_v3.state import BotState

LOG_PATH = Path('tick_vampire_v3/tick_vampire.log')
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()])


def in_active_session():
    if IGNORE_SESSIONS:
        return 'ALWAYS_ON'
    now = datetime.now(timezone.utc).strftime('%H:%M')
    for session in SESSIONS:
        if session['start'] <= now <= session['end']:
            return session['name']
    return None


def create_exchange():
    return getattr(ccxt, EXCHANGE)({'enableRateLimit': True})


def fetch_snapshot(exchange, symbol):
    ticker = exchange.fetch_ticker(symbol)
    order_book = exchange.fetch_order_book(symbol, limit=10)
    return ticker, order_book


def update_open_trade(open_trade, last_price):
    open_trade['bars_held'] += 1
    if open_trade['direction'] == 'LONG':
        move_pct = (last_price - open_trade['entry']) / open_trade['entry']
        open_trade['best_price'] = max(open_trade['best_price'], last_price)
        best_move_pct = (open_trade['best_price'] - open_trade['entry']) / open_trade['entry']
        if best_move_pct >= BREAKEVEN_TRIGGER_PCT:
            open_trade['sl'] = max(open_trade['sl'], open_trade['entry'])
        if best_move_pct >= TRAILING_TRIGGER_PCT:
            trail_floor = open_trade['best_price'] * (1 - TRAILING_GIVEBACK_PCT)
            open_trade['sl'] = max(open_trade['sl'], trail_floor)
        if last_price >= open_trade['tp']:
            return open_trade['tp'], 'TP', True
        if last_price <= open_trade['sl']:
            return open_trade['sl'], 'SL', True
        if open_trade['bars_held'] <= EARLY_FAIL_BARS and move_pct <= -BREAKEVEN_TRIGGER_PCT:
            return last_price, 'EARLY_FAIL', True
    else:
        move_pct = (open_trade['entry'] - last_price) / open_trade['entry']
        open_trade['best_price'] = min(open_trade['best_price'], last_price)
        best_move_pct = (open_trade['entry'] - open_trade['best_price']) / open_trade['entry']
        if best_move_pct >= BREAKEVEN_TRIGGER_PCT:
            open_trade['sl'] = min(open_trade['sl'], open_trade['entry'])
        if best_move_pct >= TRAILING_TRIGGER_PCT:
            trail_ceiling = open_trade['best_price'] * (1 + TRAILING_GIVEBACK_PCT)
            open_trade['sl'] = min(open_trade['sl'], trail_ceiling)
        if last_price <= open_trade['tp']:
            return open_trade['tp'], 'TP', True
        if last_price >= open_trade['sl']:
            return open_trade['sl'], 'SL', True
        if open_trade['bars_held'] <= EARLY_FAIL_BARS and move_pct <= -BREAKEVEN_TRIGGER_PCT:
            return last_price, 'EARLY_FAIL', True

    if time.time() - open_trade['opened_at'] >= MAX_HOLD_SECONDS:
        return last_price, 'TIME', True
    return last_price, 'HOLD', False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', default=True)
    args = parser.parse_args()

    init_db()
    exchange = create_exchange()
    state = BotState(balance=INITIAL_BALANCE, session_open_balance=INITIAL_BALANCE, session_peak_balance=INITIAL_BALANCE)
    closes = deque(maxlen=max(RSI_PERIOD + 5, PRICE_WINDOW + 2))
    volumes = deque(maxlen=VOLUME_MA_PERIOD + 5)
    open_trade = None
    skipped = 0
    best = 0.0
    worst = 0.0
    current_session = None
    reason_counts = {}

    logging.info('Tick Vampire v3 block 5 started | dry_run=%s | exchange=%s | symbol=%s', args.dry_run, EXCHANGE, SYMBOL)

    while True:
        session_name = in_active_session()
        if not session_name:
            logging.info('outside active session')
            time.sleep(10)
            continue

        if current_session != session_name:
            logging.info('entering session %s', session_name)
            current_session = session_name
            state.session_open_balance = state.balance
            state.session_peak_balance = state.balance
            state.total_trades_today = 0
            state.wins_today = 0
            state.losses_today = 0
            skipped = 0
            best = 0.0
            worst = 0.0
            reason_counts = {}

        ok, reason = risk_checks(state)
        if not ok:
            logging.warning('risk blocked: %s', reason)
            time.sleep(10)
            continue
        if news_blackout_active():
            logging.info('news blackout active')
            time.sleep(10)
            continue

        try:
            ticker, order_book = fetch_snapshot(exchange, SYMBOL)
        except Exception as exc:
            logging.warning('fetch error: %s', exc)
            time.sleep(5)
            continue

        last_price = ticker.get('last') or ticker.get('close') or 0.0
        bid = ticker.get('bid') or last_price
        ask = ticker.get('ask') or last_price
        spread = max(ask - bid, 0.0)
        volume = ticker.get('quoteVolume') or ticker.get('baseVolume') or 0.0
        funding_rate = ticker.get('fundingRate') or 0.0

        closes.append(last_price)
        volumes.append(volume)
        state.hourly_volume = volume
        state.volume_7d_avg = max(volume, 1.0)

        if open_trade is None and len(closes) >= RSI_PERIOD + 1 and len(volumes) >= VOLUME_MA_PERIOD:
            rsi = simple_rsi(list(closes), RSI_PERIOD)
            volume_ma = sum(list(volumes)[-VOLUME_MA_PERIOD:]) / VOLUME_MA_PERIOD
            analysis = analyze_entry_signal(order_book, list(closes), rsi, volume, volume_ma, spread, last_price, funding_rate)
            direction = analysis.get('direction')
            reason_key = analysis.get('reason', 'unknown')
            reason_counts[reason_key] = reason_counts.get(reason_key, 0) + 1
            logging.info('signal_check session=%s price=%s spread=%s rsi=%.2f volume=%s volume_ma=%s funding=%s direction=%s reason=%s', session_name, last_price, spread, rsi, volume, round(volume_ma, 4), funding_rate, direction, reason_key)
            if direction:
                reduced = state.reduced_size_trades_remaining > 0
                trade = execute_trade(direction, state.balance, last_price, reduced=reduced)
                trade['opened_at'] = time.time()
                trade['session'] = session_name
                trade['bars_held'] = 0
                trade['best_price'] = last_price
                trade['signal_reason'] = reason_key
                open_trade = trade
                logging.info('OPEN %s size=%s entry=%s tp=%s sl=%s fee=%s reason=%s', direction, trade['size'], trade['entry'], trade['tp'], trade['sl'], trade['fee'], reason_key)
            else:
                skipped += 1

        elif open_trade is not None:
            exit_price, reason_exit, closed = update_open_trade(open_trade, last_price)
            logging.info('position_check direction=%s last=%s tp=%s sl=%s reason=%s bars=%s closed=%s', open_trade['direction'], last_price, open_trade['tp'], open_trade['sl'], reason_exit, open_trade['bars_held'], closed)
            if closed:
                if open_trade['direction'] == 'LONG':
                    gross = (exit_price - open_trade['entry']) * open_trade['size']
                else:
                    gross = (open_trade['entry'] - exit_price) * open_trade['size']
                fee = open_trade['fee']
                pnl = gross - fee
                state.balance += pnl
                state.total_trades_today += 1
                state.total_trades_7d += 1
                if pnl >= 0:
                    state.wins_today += 1
                    state.wins_7d += 1
                    state.consecutive_losses = 0
                else:
                    state.losses_today += 1
                    state.consecutive_losses += 1
                    if state.consecutive_losses >= 2:
                        state.reduced_size_trades_remaining = 4
                if state.reduced_size_trades_remaining > 0:
                    state.reduced_size_trades_remaining -= 1
                state.session_peak_balance = max(state.session_peak_balance, state.balance)
                best = max(best, pnl)
                worst = min(worst, pnl)
                insert_trade((datetime.now(timezone.utc).isoformat(), open_trade['direction'], open_trade['entry'], exit_price, open_trade['size'], pnl, fee, reason_exit, session_name, state.balance))
                logging.info('CLOSE %s pnl=%s gross=%s fee=%s reason=%s balance=%s signal_reason=%s', open_trade['direction'], round(pnl, 6), round(gross, 6), round(fee, 6), reason_exit, round(state.balance, 6), open_trade.get('signal_reason'))
                open_trade = None

        time.sleep(10)


if __name__ == '__main__':
    main()
