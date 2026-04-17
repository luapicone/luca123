import argparse
import csv
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ccxt

from reversion_scalp_v1_aggressive.config import (
    BACKTEST_REPORT,
    EQUITY_CURVE_CSV,
    EXCHANGE_ID,
    INITIAL_BALANCE,
    MAX_CONCURRENT_TRADES,
    MAX_CONCURRENT_TRADES_PER_SYMBOL,
    SYMBOLS,
    SYMBOL_COOLDOWN_MINUTES,
    SYMBOL_REPEAT_LOSS_COOLDOWN_MINUTES,
    TF_CONTEXT,
    TF_ENTRY,
)
from reversion_scalp_v1_aggressive.execution import build_trade
from reversion_scalp_v1_aggressive.exit_manager import manage_exit
from reversion_scalp_v1_aggressive.indicators import rsi
from reversion_scalp_v1_aggressive.risk import risk_checks
from reversion_scalp_v1_aggressive.scanner import scan_all_assets
from reversion_scalp_v1_aggressive.state import BotState

TRADES_CSV = Path('reversion_scalp_v1_aggressive_backtest_trades.csv')
DEBUG_CSV = Path('reversion_scalp_v1_aggressive_backtest_debug.csv')
TIMEFRAME_MS = {'5m': 5 * 60 * 1000, '15m': 15 * 60 * 1000}
SCAN_STEP_MS = 20 * 1000


def create_exchange():
    return getattr(ccxt, EXCHANGE_ID)({'enableRateLimit': True})


def fetch_all_ohlcv(exchange, symbol, timeframe, since_ms, until_ms=None, limit=1000):
    rows = []
    cursor = since_ms
    step = TIMEFRAME_MS[timeframe]
    until_ms = until_ms or int(datetime.now(timezone.utc).timestamp() * 1000)
    while cursor < until_ms:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=limit)
        if not batch:
            break
        batch = [r for r in batch if r[0] >= cursor]
        if rows:
            batch = [r for r in batch if r[0] > rows[-1][0]]
        if not batch:
            cursor += step * limit
            continue
        rows.extend(batch)
        cursor = batch[-1][0] + step
        if batch[-1][0] >= until_ms - step:
            break
    return rows


def next_bar_after(rows, ts):
    for row in rows:
        if row[0] > ts:
            return row
    return None


def get_window(rows, ts, size=120):
    eligible = [r for r in rows if r[0] <= ts]
    return eligible[-size:] if len(eligible) >= size else []


def partialize_current_candle(window_5m, scan_ts):
    if not window_5m:
        return []
    base = window_5m[-1]
    start_ts = base[0]
    progress = max(0.0, min(1.0, (scan_ts - start_ts) / TIMEFRAME_MS[TF_ENTRY]))
    if progress <= 0:
        return window_5m[:-1] + [[base[0], base[1], base[1], base[1], base[1], max(base[5] * 0.05, 1.0)]]

    o, h, l, c, v = base[1], base[2], base[3], base[4], base[5]
    if c >= o:
        partial_close = o + ((h - o) * min(progress * 1.2, 1.0))
        partial_high = max(o, partial_close)
        partial_low = min(o, l + (o - l) * max(0.0, 1.0 - progress * 1.1))
    else:
        partial_close = o - ((o - l) * min(progress * 1.2, 1.0))
        partial_low = min(o, partial_close)
        partial_high = max(o, h - (h - o) * max(0.0, 1.0 - progress * 1.1))

    synthetic = [base[0], o, max(partial_high, partial_close, o), min(partial_low, partial_close, o), partial_close, max(v * max(progress, 0.05), 1.0)]
    return window_5m[:-1] + [synthetic]


def build_snapshot(data_5m, data_15m, symbols, scan_ts):
    symbol_to_candles_5m = {}
    symbol_to_candles_15m = {}
    for symbol in symbols:
        candles15 = get_window(data_15m[symbol], scan_ts, size=120)
        candles5 = get_window(data_5m[symbol], scan_ts, size=120)
        if len(candles5) < 120 or len(candles15) < 20:
            continue
        symbol_to_candles_5m[symbol] = partialize_current_candle(candles5, scan_ts)
        symbol_to_candles_15m[symbol] = candles15
    return symbol_to_candles_5m, symbol_to_candles_15m


def intrabar_points(candle, direction):
    o, h, l, c = candle[1], candle[2], candle[3], candle[4]
    if direction == 'LONG':
        return [o, min(o, (o + l) / 2), l, (l + o) / 2, max(o, (o + h) / 2), h, (h + c) / 2, c]
    return [o, max(o, (o + h) / 2), h, (h + o) / 2, min(o, (o + l) / 2), l, (l + c) / 2, c]


def run_backtest(days=30, symbols=None):
    exchange = create_exchange()
    symbols = symbols or SYMBOLS
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_ms = int(since.timestamp() * 1000)
    until_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    data_5m = {symbol: fetch_all_ohlcv(exchange, symbol, TF_ENTRY, since_ms, until_ms) for symbol in symbols}
    data_15m = {symbol: fetch_all_ohlcv(exchange, symbol, TF_CONTEXT, since_ms, until_ms) for symbol in symbols}

    first_ts = min(rows[0][0] for rows in data_5m.values() if rows)
    last_ts = max(rows[-1][0] for rows in data_5m.values() if rows)

    state = BotState(balance=INITIAL_BALANCE, daily_start_balance=INITIAL_BALANCE, session_peak_balance=INITIAL_BALANCE)
    pending_trades = []
    trades = []
    equity = []
    debug_rows = []

    required_warmup_ms = max(120 * TIMEFRAME_MS[TF_ENTRY], 20 * TIMEFRAME_MS[TF_CONTEXT])
    scan_ts = first_ts + required_warmup_ms
    while scan_ts <= last_ts:
        timestamp = datetime.fromtimestamp(scan_ts / 1000, tz=timezone.utc)

        activated = []
        keep_pending = []
        for pending in pending_trades:
            if pending['activate_at'] <= scan_ts and len(state.open_trades) < MAX_CONCURRENT_TRADES:
                trade = pending['trade']
                trade['opened_at'] = timestamp
                state.open_trades.append(trade)
                activated.append(trade['symbol'])
            else:
                keep_pending.append(pending)
        pending_trades = keep_pending

        symbol_to_candles_5m, symbol_to_candles_15m = build_snapshot(data_5m, data_15m, symbols, scan_ts)
        ok, risk_reason = risk_checks(state)
        signal = None
        diagnostics = {}

        if ok and len(state.open_trades) < MAX_CONCURRENT_TRADES and symbol_to_candles_5m:
            signal, diagnostics = scan_all_assets(symbol_to_candles_5m, symbol_to_candles_15m)
            if signal:
                cooldown_key = f"{signal['symbol']}|{signal['direction']}"
                cooldown_until = state.symbol_cooldowns.get(cooldown_key)
                same_symbol_open = sum(1 for t in state.open_trades if t['symbol'] == signal['symbol'])
                same_symbol_pending = sum(1 for t in pending_trades if t['trade']['symbol'] == signal['symbol'])
                if same_symbol_open + same_symbol_pending >= MAX_CONCURRENT_TRADES_PER_SYMBOL:
                    diagnostics[signal['symbol']] = {'rejected': 'max_open_trades_per_symbol'}
                    signal = None
                elif cooldown_until and timestamp.timestamp() < cooldown_until:
                    diagnostics[signal['symbol']] = {'rejected': 'symbol_direction_cooldown'}
                    signal = None
                else:
                    trade = build_trade(signal, state.balance)
                    if trade:
                        next_row = next_bar_after(data_5m[signal['symbol']], scan_ts)
                        if next_row is not None:
                            pending_trades.append({'trade': trade, 'activate_at': next_row[0]})
                        else:
                            diagnostics[signal['symbol']] = {'rejected': 'no_next_bar'}
                    else:
                        diagnostics[signal['symbol']] = {'rejected': 'trade_build_failed'}
                        signal = None

        remaining_open = []
        closed_count = 0
        for open_trade in state.open_trades:
            latest_bar = get_window(data_5m[open_trade['symbol']], scan_ts, size=1)
            if not latest_bar:
                remaining_open.append(open_trade)
                continue
            candle = latest_bar[-1]
            if candle[0] <= int(open_trade['opened_at'].timestamp() * 1000):
                remaining_open.append(open_trade)
                continue

            base_window = get_window(data_5m[open_trade['symbol']], scan_ts, size=120)
            rsi_5m = rsi([c[4] for c in base_window], 14)
            closed = False
            exit_price = candle[4]
            exit_reason = 'HOLD'
            for point in intrabar_points(candle, open_trade['direction']):
                synthetic_candle = [candle[0], candle[1], max(candle[1], point), min(candle[1], point), point, candle[5]]
                minutes_elapsed = (datetime.fromtimestamp((candle[0] + TIMEFRAME_MS[TF_ENTRY]) / 1000, tz=timezone.utc) - open_trade['opened_at']).total_seconds() / 60.0
                exit_price, exit_reason, closed = manage_exit(open_trade, point, synthetic_candle, minutes_elapsed, rsi_5m)
                if closed:
                    break

            if closed:
                gross = (exit_price - open_trade['entry']) * open_trade['size'] if open_trade['direction'] == 'LONG' else (open_trade['entry'] - exit_price) * open_trade['size']
                fee = open_trade['fee'] + open_trade['slippage']
                pnl = gross - fee
                state.balance += pnl
                state.session_peak_balance = max(state.session_peak_balance, state.balance)
                state.trades_today += 1
                state.consecutive_losses = state.consecutive_losses + 1 if pnl <= 0 else 0
                cooldown_key = f"{open_trade['symbol']}|{open_trade['direction']}"
                cooldown_minutes = SYMBOL_REPEAT_LOSS_COOLDOWN_MINUTES if pnl <= 0 else SYMBOL_COOLDOWN_MINUTES
                state.symbol_cooldowns[cooldown_key] = timestamp.timestamp() + (cooldown_minutes * 60)
                trades.append({
                    'timestamp': timestamp.isoformat(),
                    'symbol': open_trade['symbol'],
                    'direction': open_trade['direction'],
                    'entry_price': open_trade['entry'],
                    'exit_price': exit_price,
                    'size': open_trade['size'],
                    'pnl': pnl,
                    'fee': fee,
                    'exit_reason': exit_reason,
                    'balance_after': state.balance,
                    'score': open_trade.get('score'),
                    'stretch': open_trade.get('stretch'),
                    'context_rsi': open_trade.get('context_rsi'),
                    'zscore': open_trade.get('zscore'),
                    'hold_minutes': minutes_elapsed,
                    'mfe': open_trade.get('mfe'),
                    'mae': open_trade.get('mae'),
                    'peak_progress': open_trade.get('peak_progress'),
                })
                closed_count += 1
            else:
                remaining_open.append(open_trade)
        state.open_trades = remaining_open

        debug_rows.append({
            'timestamp': timestamp.isoformat(),
            'open_trades': len(state.open_trades),
            'pending_trades': len(pending_trades),
            'activated': ','.join(activated),
            'selected_symbol': signal['symbol'] if signal else '',
            'selected_direction': signal['direction'] if signal else '',
            'selected_score': round(signal['score'], 6) if signal else '',
            'closed_trades': closed_count,
            'balance': round(state.balance, 6),
            'risk_ok': ok,
            'risk_reason': risk_reason or '',
            'diagnostics_count': len(diagnostics),
        })
        equity.append((timestamp.isoformat(), state.balance, len(state.open_trades), len(pending_trades)))
        scan_ts += SCAN_STEP_MS

    coverage = {}
    for symbol in symbols:
        first_5m = datetime.fromtimestamp(data_5m[symbol][0][0] / 1000, tz=timezone.utc).isoformat() if data_5m[symbol] else 'none'
        last_5m = datetime.fromtimestamp(data_5m[symbol][-1][0] / 1000, tz=timezone.utc).isoformat() if data_5m[symbol] else 'none'
        first_15m = datetime.fromtimestamp(data_15m[symbol][0][0] / 1000, tz=timezone.utc).isoformat() if data_15m[symbol] else 'none'
        last_15m = datetime.fromtimestamp(data_15m[symbol][-1][0] / 1000, tz=timezone.utc).isoformat() if data_15m[symbol] else 'none'
        coverage[symbol] = {
            'candles_5m': len(data_5m[symbol]),
            'candles_15m': len(data_15m[symbol]),
            'first_5m': first_5m,
            'last_5m': last_5m,
            'first_15m': first_15m,
            'last_15m': last_15m,
        }
    return trades, equity, coverage, debug_rows


def write_outputs(trades, equity, coverage, debug_rows):
    wins = sum(1 for t in trades if t['pnl'] > 0)
    losses = sum(1 for t in trades if t['pnl'] <= 0)
    total_pnl = sum(t['pnl'] for t in trades)
    wr = (wins / len(trades) * 100) if trades else 0.0

    by_symbol = defaultdict(list)
    by_exit = defaultdict(list)
    for t in trades:
        by_symbol[t['symbol']].append(t['pnl'])
        by_exit[t['exit_reason']].append(t['pnl'])

    lines = [
        '===== REVERSION SCALP V1 AGGRESSIVE LIVE-LIKE REPLAY =====',
        f'trades: {len(trades)}',
        f'wins: {wins}',
        f'losses: {losses}',
        f'win_rate_pct: {wr:.2f}',
        f'total_pnl: {total_pnl:.6f}',
        '',
        '===== DATA COVERAGE =====',
    ]
    for symbol, info in coverage.items():
        lines.append(f"{symbol}: candles_5m={info['candles_5m']} range_5m={info['first_5m']} -> {info['last_5m']} | candles_15m={info['candles_15m']} range_15m={info['first_15m']} -> {info['last_15m']}")
    lines += ['', '===== PNL BY SYMBOL =====']
    for symbol, pnls in sorted(by_symbol.items(), key=lambda item: sum(item[1]), reverse=True):
        wins_symbol = sum(1 for pnl in pnls if pnl > 0)
        wr_symbol = (wins_symbol / len(pnls) * 100) if pnls else 0.0
        lines.append(f'{symbol}: trades={len(pnls)} pnl={sum(pnls):.6f} avg={sum(pnls)/len(pnls):.6f} win_rate_pct={wr_symbol:.2f}')
    lines += ['', '===== EXIT REASONS =====']
    for reason, pnls in sorted(by_exit.items(), key=lambda item: len(item[1]), reverse=True):
        lines.append(f'{reason}: trades={len(pnls)} pnl={sum(pnls):.6f}')
    BACKTEST_REPORT.write_text('\n'.join(lines), encoding='utf8')

    with TRADES_CSV.open('w', newline='', encoding='utf8') as f:
        writer = csv.DictWriter(f, fieldnames=list(trades[0].keys()) if trades else ['timestamp'])
        writer.writeheader()
        if trades:
            writer.writerows(trades)

    with EQUITY_CURVE_CSV.open('w', newline='', encoding='utf8') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp', 'balance', 'open_trades', 'pending_trades'])
        writer.writerows(equity)

    with DEBUG_CSV.open('w', newline='', encoding='utf8') as f:
        writer = csv.DictWriter(f, fieldnames=list(debug_rows[0].keys()) if debug_rows else ['timestamp'])
        writer.writeheader()
        if debug_rows:
            writer.writerows(debug_rows)

    print(f'Backtest report generated: {BACKTEST_REPORT}')
    print(f'Trades CSV generated: {TRADES_CSV}')
    print(f'Equity curve generated: {EQUITY_CURVE_CSV}')
    print(f'Debug CSV generated: {DEBUG_CSV}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=30)
    parser.add_argument('--symbol', action='append', dest='symbols')
    args = parser.parse_args()
    trades, equity, coverage, debug_rows = run_backtest(days=args.days, symbols=args.symbols)
    write_outputs(trades, equity, coverage, debug_rows)


if __name__ == '__main__':
    main()
