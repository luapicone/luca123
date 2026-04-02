import argparse
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ccxt

from reversion_scalp_v1.config import (
    BACKTEST_REPORT,
    EQUITY_CURVE_CSV,
    EXCHANGE_ID,
    INITIAL_BALANCE,
    SYMBOLS,
    TF_CONTEXT,
    TF_ENTRY,
    SYMBOL_COOLDOWN_MINUTES,
    SYMBOL_REPEAT_LOSS_COOLDOWN_MINUTES,
)
from reversion_scalp_v1.execution import build_trade
from reversion_scalp_v1.exit_manager import manage_exit
from reversion_scalp_v1.indicators import rsi
from reversion_scalp_v1.risk import risk_checks
from reversion_scalp_v1.scanner import scan_all_assets
from reversion_scalp_v1.signal import detect_reversion_signal
from reversion_scalp_v1.state import BotState

TRADES_CSV = Path('reversion_scalp_v1_backtest_trades.csv')


def create_exchange():
    return getattr(ccxt, EXCHANGE_ID)({'enableRateLimit': True})


TIMEFRAME_MS = {'5m': 5 * 60 * 1000, '15m': 15 * 60 * 1000}

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


def synthesize_signal_from_partial_candle(candles_5m, candles_15m):
    if not candles_5m:
        return None
    base = candles_5m[-1]
    o, h, l, c, v = base[1], base[2], base[3], base[4], base[5]
    path = [o, (o + l) / 2, l, (l + c) / 2, (o + h) / 2, h, (h + c) / 2, c]
    candidates = []
    for idx, point in enumerate(path):
        candidates.append([base[0], o, max(o, point), min(o, point), point, max(v * ((idx + 1) / len(path)), 1.0)])
    best = None
    for partial in candidates:
        synthetic_5m = candles_5m[:-1] + [partial]
        signal = detect_reversion_signal(synthetic_5m, candles_15m)
        if signal and 'rejected' not in signal:
            if best is None or signal.get('score', 0) > best.get('score', 0):
                best = signal
    return best


def run_backtest(days=30, symbols=None):
    exchange = create_exchange()
    symbols = symbols or SYMBOLS
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_ms = int(since.timestamp() * 1000)
    until_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    data_5m = {symbol: fetch_all_ohlcv(exchange, symbol, TF_ENTRY, since_ms, until_ms) for symbol in symbols}
    data_15m = {symbol: fetch_all_ohlcv(exchange, symbol, TF_CONTEXT, since_ms, until_ms) for symbol in symbols}

    state = BotState(balance=INITIAL_BALANCE, daily_start_balance=INITIAL_BALANCE, session_peak_balance=INITIAL_BALANCE)
    open_trade = None
    pending_trade = None
    trades = []
    equity = []

    all_times = sorted({row[0] for symbol in symbols for row in data_5m[symbol]})

    for ts in all_times:
        timestamp = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        symbol_to_candles_5m = {}
        symbol_to_candles_15m = {}

        for symbol in symbols:
            candles5 = [c for c in data_5m[symbol] if c[0] <= ts]
            candles15 = [c for c in data_15m[symbol] if c[0] <= ts]
            if len(candles5) >= 120 and len(candles15) >= 120:
                symbol_to_candles_5m[symbol] = candles5[-120:]
                symbol_to_candles_15m[symbol] = candles15[-120:]

        if pending_trade and pending_trade['activate_at'] == ts and open_trade is None:
            trade = pending_trade['trade']
            trade['opened_at'] = timestamp
            open_trade = trade
            pending_trade = None

        if open_trade is None and pending_trade is None:
            ok, _ = risk_checks(state)
            if ok and symbol_to_candles_5m:
                candidates = []
                diagnostics = {}
                for symbol, candles5 in symbol_to_candles_5m.items():
                    signal = synthesize_signal_from_partial_candle(candles5, symbol_to_candles_15m.get(symbol, []))
                    if signal:
                        signal['symbol'] = symbol
                        candidates.append(signal)
                    else:
                        diagnostics[symbol] = {'rejected': 'no_partial_or_close_signal'}
                signal = sorted(candidates, key=lambda x: x['score'], reverse=True)[0] if candidates else None
                if signal:
                    cooldown_key = f"{signal['symbol']}|{signal['direction']}"
                    cooldown_until = state.symbol_cooldowns.get(cooldown_key)
                    now_ts = timestamp.timestamp()
                    if not cooldown_until or now_ts >= cooldown_until:
                        trade = build_trade(signal, state.balance)
                        if trade:
                            next_ts = None
                            symbol_rows = data_5m[signal['symbol']]
                            for row in symbol_rows:
                                if row[0] > ts:
                                    next_ts = row[0]
                                    break
                            if next_ts is not None:
                                pending_trade = {'trade': trade, 'activate_at': next_ts}
        elif open_trade is not None:
            candles = symbol_to_candles_5m.get(open_trade['symbol'])
            if candles and candles[-1][0] > int(open_trade['opened_at'].timestamp() * 1000):
                candle = candles[-1]
                minutes_elapsed = (timestamp - open_trade['opened_at']).total_seconds() / 60.0
                rsi_5m = rsi([c[4] for c in candles], 14)
                closed = False
                exit_price = candle[4]
                exit_reason = 'HOLD'
                path_points = intrabar_path(candle, open_trade['direction'])
                for idx, point in enumerate(path_points):
                    synthetic_candle = [candle[0], candle[1], max(candle[1], point), min(candle[1], point), point, candle[5]]
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
                    open_trade = None
        equity.append((timestamp.isoformat(), state.balance))

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
        '===== REVERSION SCALP V1 BACKTEST =====',
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
        writer.writerow(['timestamp', 'balance'])
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
