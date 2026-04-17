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
)
from reversion_scalp_v1_aggressive.execution import build_trade
from reversion_scalp_v1_aggressive.exit_manager import manage_exit
from reversion_scalp_v1_aggressive.indicators import rsi
from reversion_scalp_v1_aggressive.scanner import scan_all_assets
from reversion_scalp_v1_aggressive.state import BotState

TRADES_CSV = Path('reversion_scalp_v1_aggressive_backtest_trades.csv')
DEBUG_CSV = Path('reversion_scalp_v1_aggressive_backtest_debug.csv')
TIMEFRAME_MS = {'1m': 60 * 1000, '5m': 5 * 60 * 1000, '15m': 15 * 60 * 1000}
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


def floor_time(ts, timeframe_ms):
    return ts - (ts % timeframe_ms)


def aggregate_candles(rows, timeframe_ms, end_ts_inclusive):
    grouped = defaultdict(list)
    for row in rows:
        if row[0] > end_ts_inclusive:
            break
        bucket = floor_time(row[0], timeframe_ms)
        grouped[bucket].append(row)

    candles = []
    for bucket in sorted(grouped.keys()):
        chunk = grouped[bucket]
        open_price = chunk[0][1]
        high = max(r[2] for r in chunk)
        low = min(r[3] for r in chunk)
        close = chunk[-1][4]
        volume = sum(r[5] for r in chunk)
        candles.append([bucket, open_price, high, low, close, volume])
    return candles


def build_snapshot_from_1m(data_1m, symbols, scan_ts):
    symbol_to_candles_5m = {}
    symbol_to_candles_15m = {}
    symbol_to_latest_1m = {}
    for symbol in symbols:
        rows_1m = [r for r in data_1m[symbol] if r[0] <= scan_ts]
        if len(rows_1m) < 120:
            continue
        candles_5m = aggregate_candles(rows_1m, TIMEFRAME_MS['5m'], scan_ts)
        candles_15m = aggregate_candles(rows_1m, TIMEFRAME_MS['15m'], scan_ts)
        if len(candles_5m) < 120 or len(candles_15m) < 20:
            continue
        symbol_to_candles_5m[symbol] = candles_5m[-120:]
        symbol_to_candles_15m[symbol] = candles_15m[-120:]
        symbol_to_latest_1m[symbol] = rows_1m[-1]
    return symbol_to_candles_5m, symbol_to_candles_15m, symbol_to_latest_1m


def next_1m_bar_after(rows, ts):
    for row in rows:
        if row[0] > ts:
            return row
    return None


def run_backtest(days=30, symbols=None):
    exchange = create_exchange()
    symbols = symbols or SYMBOLS
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_ms = int(since.timestamp() * 1000)
    until_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    data_1m = {symbol: fetch_all_ohlcv(exchange, symbol, '1m', since_ms, until_ms) for symbol in symbols}

    first_ts = min(rows[0][0] for rows in data_1m.values() if rows)
    last_ts = max(rows[-1][0] for rows in data_1m.values() if rows)
    required_warmup_ms = max(120 * TIMEFRAME_MS['5m'], 20 * TIMEFRAME_MS['15m'])
    scan_ts = first_ts + required_warmup_ms

    state = BotState(balance=INITIAL_BALANCE, daily_start_balance=INITIAL_BALANCE, session_peak_balance=INITIAL_BALANCE)
    pending_trades = []
    trades = []
    equity = []
    debug_rows = []

    while scan_ts <= last_ts:
        timestamp = datetime.fromtimestamp(scan_ts / 1000, tz=timezone.utc)
        activated = []
        still_pending = []
        for pending in pending_trades:
            if pending['activate_at'] <= scan_ts and len(state.open_trades) < MAX_CONCURRENT_TRADES:
                pending['trade']['opened_at'] = timestamp
                state.open_trades.append(pending['trade'])
                activated.append(pending['trade']['symbol'])
            else:
                still_pending.append(pending)
        pending_trades = still_pending

        symbol_to_candles_5m, symbol_to_candles_15m, symbol_to_latest_1m = build_snapshot_from_1m(data_1m, symbols, scan_ts)
        diagnostics = {}
        selected_signals = []

        if len(state.open_trades) < MAX_CONCURRENT_TRADES and symbol_to_candles_5m:
            candidates = []
            for symbol, candles_5m in symbol_to_candles_5m.items():
                signal, symbol_diagnostics = scan_all_assets({symbol: candles_5m}, {symbol: symbol_to_candles_15m[symbol]})
                if signal:
                    candidates.append(signal)
                elif symbol_diagnostics:
                    diagnostics[symbol] = symbol_diagnostics.get(symbol, {'rejected': 'no_signal'})

            candidates = sorted(candidates, key=lambda x: x['score'], reverse=True)
            for signal in candidates:
                if len(state.open_trades) + len(pending_trades) >= MAX_CONCURRENT_TRADES:
                    break
                cooldown_key = f"{signal['symbol']}|{signal['direction']}"
                cooldown_until = state.symbol_cooldowns.get(cooldown_key)
                same_symbol_open = sum(1 for t in state.open_trades if t['symbol'] == signal['symbol'])
                same_symbol_pending = sum(1 for t in pending_trades if t['trade']['symbol'] == signal['symbol'])
                if same_symbol_open + same_symbol_pending >= MAX_CONCURRENT_TRADES_PER_SYMBOL:
                    diagnostics[signal['symbol']] = {'rejected': 'max_open_trades_per_symbol'}
                    continue
                if cooldown_until and timestamp.timestamp() < cooldown_until:
                    diagnostics[signal['symbol']] = {'rejected': 'symbol_direction_cooldown'}
                    continue
                trade = build_trade(signal, state.balance)
                if not trade:
                    diagnostics[signal['symbol']] = {'rejected': 'trade_build_failed'}
                    continue
                next_bar = next_1m_bar_after(data_1m[signal['symbol']], scan_ts)
                if not next_bar:
                    diagnostics[signal['symbol']] = {'rejected': 'no_next_bar'}
                    continue
                pending_trades.append({'trade': trade, 'activate_at': next_bar[0]})
                selected_signals.append(signal)

        remaining_open = []
        closed_count = 0
        for open_trade in state.open_trades:
            current_1m = symbol_to_latest_1m.get(open_trade['symbol'])
            if not current_1m:
                remaining_open.append(open_trade)
                continue
            if current_1m[0] <= int(open_trade['opened_at'].timestamp() * 1000):
                remaining_open.append(open_trade)
                continue

            symbol_rows = [r for r in data_1m[open_trade['symbol']] if int(open_trade['opened_at'].timestamp() * 1000) < r[0] <= scan_ts]
            base_1m_rows = [r for r in data_1m[open_trade['symbol']] if r[0] <= scan_ts]
            candles_5m_for_rsi = aggregate_candles(base_1m_rows, TIMEFRAME_MS['5m'], scan_ts)
            rsi_5m = rsi([c[4] for c in candles_5m_for_rsi[-120:]], 14) if len(candles_5m_for_rsi) >= 15 else None
            closed = False
            exit_price = current_1m[4]
            exit_reason = 'HOLD'
            for candle_1m in symbol_rows:
                minutes_elapsed = (datetime.fromtimestamp((candle_1m[0] + TIMEFRAME_MS['1m']) / 1000, tz=timezone.utc) - open_trade['opened_at']).total_seconds() / 60.0
                exit_price, exit_reason, closed = manage_exit(open_trade, candle_1m[4], candle_1m, minutes_elapsed, rsi_5m)
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
            'activated': '|'.join(activated),
            'selected_symbol': '|'.join(s['symbol'] for s in selected_signals),
            'selected_direction': '|'.join(s['direction'] for s in selected_signals),
            'selected_score': '|'.join(str(round(s['score'], 6)) for s in selected_signals),
            'closed_trades': closed_count,
            'balance': round(state.balance, 6),
            'diagnostics_count': len(diagnostics),
        })
        equity.append((timestamp.isoformat(), state.balance, len(state.open_trades), len(pending_trades)))
        scan_ts += SCAN_STEP_MS

    coverage = {}
    for symbol in symbols:
        first_1m = datetime.fromtimestamp(data_1m[symbol][0][0] / 1000, tz=timezone.utc).isoformat() if data_1m[symbol] else 'none'
        last_1m = datetime.fromtimestamp(data_1m[symbol][-1][0] / 1000, tz=timezone.utc).isoformat() if data_1m[symbol] else 'none'
        coverage[symbol] = {
            'candles_1m': len(data_1m[symbol]),
            'first_1m': first_1m,
            'last_1m': last_1m,
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
        '===== REVERSION SCALP V1 AGGRESSIVE 1M LIVE-LIKE REPLAY =====',
        f'trades: {len(trades)}',
        f'wins: {wins}',
        f'losses: {losses}',
        f'win_rate_pct: {wr:.2f}',
        f'total_pnl: {total_pnl:.6f}',
        '',
        '===== DATA COVERAGE =====',
    ]
    for symbol, info in coverage.items():
        lines.append(f"{symbol}: candles_1m={info['candles_1m']} range_1m={info['first_1m']} -> {info['last_1m']}")
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
