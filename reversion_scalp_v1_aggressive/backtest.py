import argparse
import csv
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
TIMEFRAME_MS = {'5m': 5 * 60 * 1000, '15m': 15 * 60 * 1000}


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


def intrabar_path(candle, direction):
    open_price = candle[1]
    high = candle[2]
    low = candle[3]
    close = candle[4]
    if direction == 'LONG':
        return [open_price, (open_price + low) / 2, low, (low + high) / 2, high, (high + close) / 2, close]
    return [open_price, (open_price + high) / 2, high, (high + low) / 2, low, (low + close) / 2, close]


def next_bar_after(rows, ts):
    for row in rows:
        if row[0] > ts:
            return row[0]
    return None


def build_market_snapshot(data_5m, data_15m, symbols, ts):
    symbol_to_candles_5m = {}
    symbol_to_candles_15m = {}
    for symbol in symbols:
        candles5 = [c for c in data_5m[symbol] if c[0] <= ts]
        candles15 = [c for c in data_15m[symbol] if c[0] <= ts]
        if len(candles5) >= 120 and len(candles15) >= 120:
            symbol_to_candles_5m[symbol] = candles5[-120:]
            symbol_to_candles_15m[symbol] = candles15[-120:]
    return symbol_to_candles_5m, symbol_to_candles_15m


def run_backtest(days=30, symbols=None):
    exchange = create_exchange()
    symbols = symbols or SYMBOLS
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_ms = int(since.timestamp() * 1000)
    until_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    data_5m = {symbol: fetch_all_ohlcv(exchange, symbol, TF_ENTRY, since_ms, until_ms) for symbol in symbols}
    data_15m = {symbol: fetch_all_ohlcv(exchange, symbol, TF_CONTEXT, since_ms, until_ms) for symbol in symbols}

    state = BotState(balance=INITIAL_BALANCE, daily_start_balance=INITIAL_BALANCE, session_peak_balance=INITIAL_BALANCE)
    pending_trades = []
    trades = []
    equity = []

    all_times = sorted({row[0] for symbol in symbols for row in data_5m[symbol]})

    for ts in all_times:
        timestamp = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        symbol_to_candles_5m, symbol_to_candles_15m = build_market_snapshot(data_5m, data_15m, symbols, ts)

        # activate pending entries on their next candle
        still_pending = []
        for pending in pending_trades:
            if pending['activate_at'] == ts and len(state.open_trades) < MAX_CONCURRENT_TRADES:
                pending['trade']['opened_at'] = timestamp
                state.open_trades.append(pending['trade'])
            else:
                still_pending.append(pending)
        pending_trades = still_pending

        ok, _ = risk_checks(state)
        if ok and len(state.open_trades) < MAX_CONCURRENT_TRADES and symbol_to_candles_5m:
            signal_candidates = []
            diagnostics = {}
            for symbol in symbols:
                if symbol not in symbol_to_candles_5m:
                    continue
                signal, symbol_diag = scan_all_assets({symbol: symbol_to_candles_5m[symbol]}, {symbol: symbol_to_candles_15m[symbol]})
                if signal:
                    signal_candidates.append(signal)
                else:
                    diagnostics[symbol] = symbol_diag.get(symbol, {'rejected': 'no_signal'}) if isinstance(symbol_diag, dict) else {'rejected': 'no_signal'}

            signal_candidates = sorted(signal_candidates, key=lambda x: x['score'], reverse=True)
            for signal in signal_candidates:
                if len(state.open_trades) + len(pending_trades) >= MAX_CONCURRENT_TRADES:
                    break
                cooldown_key = f"{signal['symbol']}|{signal['direction']}"
                cooldown_until = state.symbol_cooldowns.get(cooldown_key)
                now_ts = timestamp.timestamp()
                same_symbol_open = sum(1 for t in state.open_trades if t['symbol'] == signal['symbol'])
                same_symbol_pending = sum(1 for t in pending_trades if t['trade']['symbol'] == signal['symbol'])
                if same_symbol_open + same_symbol_pending >= MAX_CONCURRENT_TRADES_PER_SYMBOL:
                    continue
                if cooldown_until and now_ts < cooldown_until:
                    continue
                trade = build_trade(signal, state.balance)
                if not trade:
                    continue
                next_ts = next_bar_after(data_5m[signal['symbol']], ts)
                if next_ts is None:
                    continue
                pending_trades.append({'trade': trade, 'activate_at': next_ts})

        remaining_open_trades = []
        for open_trade in state.open_trades:
            candles = symbol_to_candles_5m.get(open_trade['symbol'])
            if not candles:
                remaining_open_trades.append(open_trade)
                continue
            latest_candle = candles[-1]
            if latest_candle[0] <= int(open_trade['opened_at'].timestamp() * 1000):
                remaining_open_trades.append(open_trade)
                continue

            minutes_elapsed = (timestamp - open_trade['opened_at']).total_seconds() / 60.0
            rsi_5m = rsi([c[4] for c in candles], 14)
            exit_price = latest_candle[4]
            exit_reason = 'HOLD'
            closed = False
            for point in intrabar_path(latest_candle, open_trade['direction']):
                synthetic_candle = [latest_candle[0], latest_candle[1], max(latest_candle[1], point), min(latest_candle[1], point), point, latest_candle[5]]
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
            else:
                remaining_open_trades.append(open_trade)
        state.open_trades = remaining_open_trades
        equity.append((timestamp.isoformat(), state.balance, len(state.open_trades), len(pending_trades)))

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
    return trades, equity, coverage


def write_outputs(trades, equity, coverage):
    wins = sum(1 for t in trades if t['pnl'] > 0)
    losses = sum(1 for t in trades if t['pnl'] <= 0)
    total_pnl = sum(t['pnl'] for t in trades)
    wr = (wins / len(trades) * 100) if trades else 0.0

    by_symbol = {}
    by_exit = {}
    for t in trades:
        by_symbol.setdefault(t['symbol'], []).append(t['pnl'])
        by_exit.setdefault(t['exit_reason'], []).append(t['pnl'])

    lines = [
        '===== REVERSION SCALP V1 AGGRESSIVE BACKTEST =====',
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
        lines.append(f'{symbol}: trades={len(pnls)} pnl={sum(pnls):.6f} avg={sum(pnls)/len(pnls):.6f}')
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

    print(f'Backtest report generated: {BACKTEST_REPORT}')
    print(f'Trades CSV generated: {TRADES_CSV}')
    print(f'Equity curve generated: {EQUITY_CURVE_CSV}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=30)
    parser.add_argument('--symbol', action='append', dest='symbols')
    args = parser.parse_args()
    trades, equity, coverage = run_backtest(days=args.days, symbols=args.symbols)
    write_outputs(trades, equity, coverage)


if __name__ == '__main__':
    main()
