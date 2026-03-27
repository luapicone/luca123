import argparse
import logging
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import ccxt

from tick_vampire_v3.calendar import news_blackout_active
from tick_vampire_v3.config import EXCHANGE, INITIAL_BALANCE, RSI_PERIOD, SESSIONS, SYMBOL, VOLUME_MA_PERIOD
from tick_vampire_v3.db import init_db, insert_trade
from tick_vampire_v3.execution import execute_trade
from tick_vampire_v3.report import format_session_report
from tick_vampire_v3.risk import risk_checks
from tick_vampire_v3.signal import check_entry_signal, simple_rsi
from tick_vampire_v3.state import BotState

LOG_PATH = Path('tick_vampire_v3/tick_vampire.log')
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()])


def in_active_session():
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


def simulate_exit(direction, entry, tp, sl, last_price):
    if direction == 'LONG':
        if last_price >= tp:
            return tp, 'TP'
        if last_price <= sl:
            return sl, 'SL'
    else:
        if last_price <= tp:
            return tp, 'TP'
        if last_price >= sl:
            return sl, 'SL'
    return last_price, 'TIME'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', default=True)
    args = parser.parse_args()

    init_db()
    exchange = create_exchange()
    state = BotState(balance=INITIAL_BALANCE, session_open_balance=INITIAL_BALANCE, session_peak_balance=INITIAL_BALANCE)
    closes = deque(maxlen=RSI_PERIOD + 5)
    volumes = deque(maxlen=VOLUME_MA_PERIOD + 5)
    open_trade = None
    skipped = 0
    best = 0.0
    worst = 0.0
    current_session = None

    logging.info('Tick Vampire v3 block 4 started | dry_run=%s | exchange=%s | symbol=%s', args.dry_run, EXCHANGE, SYMBOL)

    while True:
        session_name = in_active_session()
        if not session_name:
            logging.info('outside active session')
            if current_session is not None:
                report = format_session_report({
                    'datetime': datetime.now(timezone.utc).isoformat(),
                    'session': current_session,
                    'trades': state.total_trades_today,
                    'wins': state.wins_today,
                    'losses': state.losses_today,
                    'wr': round((state.wins_today / max(state.total_trades_today, 1)) * 100, 2),
                    'pnl': round(state.balance - state.session_open_balance, 6),
                    'pnl_pct': round(((state.balance - state.session_open_balance) / max(state.session_open_balance, 1e-9)) * 100, 4),
                    'start': round(state.session_open_balance, 6),
                    'end': round(state.balance, 6),
                    'best': round(best, 6),
                    'worst': round(worst, 6),
                    'skipped': skipped,
                    'halt': state.halt_reason or 'no',
                })
                print(report)
                current_session = None
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
            direction = check_entry_signal(order_book, rsi, volume, volume_ma, spread, last_price, funding_rate)
            logging.info('signal_check session=%s price=%s spread=%s rsi=%.2f volume=%s volume_ma=%s funding=%s direction=%s', session_name, last_price, spread, rsi, volume, round(volume_ma, 4), funding_rate, direction)
            if direction:
                reduced = state.reduced_size_trades_remaining > 0
                trade = execute_trade(direction, state.balance, last_price, reduced=reduced)
                trade['opened_at'] = time.time()
                trade['session'] = session_name
                open_trade = trade
                logging.info('OPEN %s size=%s entry=%s tp=%s sl=%s fee=%s', direction, trade['size'], trade['entry'], trade['tp'], trade['sl'], trade['fee'])
            else:
                skipped += 1

        elif open_trade is not None:
            exit_price, reason_exit = simulate_exit(open_trade['direction'], open_trade['entry'], open_trade['tp'], open_trade['sl'], last_price)
            closed = reason_exit in {'TP', 'SL'} or (time.time() - open_trade['opened_at'] >= 180)
            logging.info('position_check direction=%s last=%s tp=%s sl=%s exit_reason=%s closed=%s', open_trade['direction'], last_price, open_trade['tp'], open_trade['sl'], reason_exit, closed)
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
                    if state.consecutive_losses >= 3:
                        state.reduced_size_trades_remaining = 5
                if state.reduced_size_trades_remaining > 0:
                    state.reduced_size_trades_remaining -= 1
                state.session_peak_balance = max(state.session_peak_balance, state.balance)
                best = max(best, pnl)
                worst = min(worst, pnl)
                insert_trade((datetime.now(timezone.utc).isoformat(), open_trade['direction'], open_trade['entry'], exit_price, open_trade['size'], pnl, fee, reason_exit, session_name, state.balance))
                logging.info('CLOSE %s pnl=%s gross=%s fee=%s reason=%s balance=%s', open_trade['direction'], round(pnl, 6), round(gross, 6), round(fee, 6), reason_exit, round(state.balance, 6))
                open_trade = None

        time.sleep(10)


if __name__ == '__main__':
    main()
