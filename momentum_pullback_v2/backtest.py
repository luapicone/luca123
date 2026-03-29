import argparse
import csv
import math
from pathlib import Path

from momentum_pullback_v2.config import BACKTEST_REPORT, EQUITY_CURVE_CSV, INITIAL_BALANCE, SLIPPAGE_PCT, SYMBOLS, TF_CONTEXT, TF_ENTRY
from momentum_pullback_v2.execution import build_trade
from momentum_pullback_v2.exit_manager import manage_exit
from momentum_pullback_v2.indicators import rsi
from momentum_pullback_v2.scanner import scan_all_assets


def load_ohlcv_csv(path):
    rows = []
    with open(path, 'r', encoding='utf8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append([
                int(row['timestamp']),
                float(row['open']),
                float(row['high']),
                float(row['low']),
                float(row['close']),
                float(row['volume']),
            ])
    return rows


def sharpe_ratio(returns):
    if not returns:
        return 0.0
    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / max(len(returns) - 1, 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return mean_r / std * math.sqrt(len(returns))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', required=True, help='Directory with per-symbol CSVs named like BTCUSDT_5m.csv and BTCUSDT_15m.csv')
    args = parser.parse_args()
    data_dir = Path(args.data_dir)

    symbol_data_5m = {}
    symbol_data_15m = {}
    for symbol in SYMBOLS:
        compact = symbol.replace('/USDT:USDT', 'USDT')
        path_5m = data_dir / f'{compact}_{TF_ENTRY}.csv'
        path_15m = data_dir / f'{compact}_{TF_CONTEXT}.csv'
        if not path_5m.exists() or not path_15m.exists():
            raise FileNotFoundError(f'Missing CSVs for {symbol}: {path_5m} {path_15m}')
        symbol_data_5m[symbol] = load_ohlcv_csv(path_5m)
        symbol_data_15m[symbol] = load_ohlcv_csv(path_15m)

    balance = INITIAL_BALANCE
    equity = []
    returns = []
    trades = []
    open_trade = None
    max_equity = balance
    max_drawdown = 0.0
    min_len = min(len(v) for v in symbol_data_5m.values())

    for i in range(100, min_len):
        symbol_to_candles_5m = {s: symbol_data_5m[s][:i] for s in SYMBOLS}
        symbol_to_candles_15m = {s: symbol_data_15m[s][: max(40, i // 3)] for s in SYMBOLS}
        if open_trade is None:
            signal, diagnostics = scan_all_assets(symbol_to_candles_5m, symbol_to_candles_15m)
            if signal:
                open_trade = build_trade(signal, balance)
                if open_trade:
                    open_trade['opened_index'] = i
        else:
            candle = symbol_data_5m[open_trade['symbol']][i]
            minutes_elapsed = (i - open_trade['opened_index']) * 5
            rsi_5m = rsi([c[4] for c in symbol_data_5m[open_trade['symbol']][:i]], 14)
            exit_price, reason, closed = manage_exit(open_trade, candle[4], candle, minutes_elapsed, rsi_5m)
            if closed:
                if open_trade['direction'] == 'LONG':
                    gross = (exit_price - open_trade['entry']) * open_trade['size']
                else:
                    gross = (open_trade['entry'] - exit_price) * open_trade['size']
                fee = open_trade['fee'] + (open_trade['entry'] * open_trade['size'] * SLIPPAGE_PCT * 2)
                pnl = gross - fee
                prev_balance = balance
                balance += pnl
                trades.append({
                    'symbol': open_trade['symbol'],
                    'direction': open_trade['direction'],
                    'pnl': pnl,
                    'reason': reason,
                    'minutes': minutes_elapsed,
                    'mfe': open_trade.get('mfe', 0.0),
                    'mae': open_trade.get('mae', 0.0),
                    'peak_progress': open_trade.get('peak_progress', 0.0),
                    'score': open_trade.get('score', 0.0),
                })
                returns.append((balance - prev_balance) / max(prev_balance, 1e-9))
                open_trade = None
        max_equity = max(max_equity, balance)
        drawdown = (max_equity - balance) / max(max_equity, 1e-9)
        max_drawdown = max(max_drawdown, drawdown)
        equity.append((i, balance))

    wins = sum(1 for t in trades if t['pnl'] > 0)
    losses = sum(1 for t in trades if t['pnl'] <= 0)
    gross_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0)
    gross_loss = abs(sum(t['pnl'] for t in trades if t['pnl'] <= 0))
    profit_factor = gross_profit / gross_loss if gross_loss else 0.0
    sharpe = sharpe_ratio(returns)
    avg_win_minutes = sum(t['minutes'] for t in trades if t['pnl'] > 0) / max(wins, 1)
    avg_loss_minutes = sum(t['minutes'] for t in trades if t['pnl'] <= 0) / max(losses, 1)
    avg_mfe = sum(t['mfe'] for t in trades) / max(len(trades), 1)
    avg_mae = sum(t['mae'] for t in trades) / max(len(trades), 1)
    avg_peak_progress = sum(t['peak_progress'] for t in trades) / max(len(trades), 1)

    by_symbol = {}
    by_reason = {}
    for t in trades:
        by_symbol.setdefault(t['symbol'], 0.0)
        by_symbol[t['symbol']] += t['pnl']
        by_reason.setdefault(t['reason'], 0)
        by_reason[t['reason']] += 1

    with EQUITY_CURVE_CSV.open('w', newline='', encoding='utf8') as f:
        writer = csv.writer(f)
        writer.writerow(['step', 'equity'])
        writer.writerows(equity)

    lines = [
        '===== MOMENTUM PULLBACK V2 BACKTEST REPORT =====',
        f'total_trades: {len(trades)}',
        f'win_rate_pct: {(wins / len(trades) * 100) if trades else 0.0:.4f}',
        f'profit_factor: {profit_factor:.4f}',
        f'max_drawdown_pct: {max_drawdown * 100:.4f}',
        f'sharpe_ratio: {sharpe:.4f}',
        f'final_balance: {balance:.6f}',
        f'avg_win_minutes: {avg_win_minutes:.2f}',
        f'avg_loss_minutes: {avg_loss_minutes:.2f}',
        f'avg_mfe: {avg_mfe:.6f}',
        f'avg_mae: {avg_mae:.6f}',
        f'avg_peak_progress: {avg_peak_progress:.4f}',
        '',
        'PNL by symbol:'
    ]
    for symbol, pnl in by_symbol.items():
        lines.append(f'{symbol}: {pnl:.6f}')
    lines.append('')
    lines.append('Exit reasons:')
    for reason, count in by_reason.items():
        lines.append(f'{reason}: {count}')
    lines.append('')
    lines.append('Binance historical CSVs can be downloaded from the Binance data portal and converted to the expected OHLCV schema: timestamp,open,high,low,close,volume.')
    BACKTEST_REPORT.write_text('\n'.join(lines), encoding='utf8')
    print(f'Backtest report generated: {BACKTEST_REPORT}')
    print(f'Equity curve saved: {EQUITY_CURVE_CSV}')


if __name__ == '__main__':
    main()
