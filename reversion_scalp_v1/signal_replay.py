import argparse
import csv
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ccxt

from reversion_scalp_v1.config import EXCHANGE_ID, SYMBOLS, TF_CONTEXT, TF_ENTRY
from reversion_scalp_v1.signal import detect_reversion_signal

REPORT_PATH = Path('reversion_scalp_v1_signal_replay_report.txt')
CSV_PATH = Path('reversion_scalp_v1_signal_replay.csv')
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


def classify_signal(row, scenario):
    tp_first = row['hit_tp'] and not row['hit_sl']
    sl_first = row['hit_sl'] and not row['hit_tp']
    both = row['hit_tp'] and row['hit_sl']
    if scenario == 'strict_tp_first':
        return tp_first
    if scenario == 'strict_sl_first':
        return not sl_first
    if scenario == 'mfe_gt_mae':
        return row['mfe'] > row['mae']
    if scenario == 'balanced':
        return (row['hit_tp'] and row['mfe'] >= row['mae']) or (row['mfe'] > row['mae'] * 1.1)
    return False


def apply_filter_variant(row, variant):
    if variant == 'baseline':
        return True
    if variant == 'higher_score':
        return (row.get('score') or 0) >= 0.6
    if variant == 'deeper_stretch':
        return abs(row.get('stretch') or 0) >= 0.00045
    if variant == 'stronger_zscore':
        return abs(row.get('zscore') or 0) >= 0.65
    return True


def replay(days=30, symbols=None, lookahead_bars=6):
    exchange = create_exchange()
    symbols = symbols or SYMBOLS
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_ms = int(since.timestamp() * 1000)
    until_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    data_5m = {symbol: fetch_all_ohlcv(exchange, symbol, TF_ENTRY, since_ms, until_ms) for symbol in symbols}
    data_15m = {symbol: fetch_all_ohlcv(exchange, symbol, TF_CONTEXT, since_ms, until_ms) for symbol in symbols}

    results = []
    for symbol in symbols:
        candles5 = data_5m[symbol]
        candles15 = data_15m[symbol]
        for i in range(120, len(candles5) - lookahead_bars):
            ts = candles5[i][0]
            context15 = [c for c in candles15 if c[0] <= ts][-120:]
            entry5 = candles5[:i + 1][-120:]
            if len(entry5) < 120 or len(context15) < 120:
                continue
            signal = detect_reversion_signal(entry5, context15)
            if not signal or 'rejected' in signal:
                continue
            future = candles5[i + 1:i + 1 + lookahead_bars]
            entry = signal['entry']
            if signal['direction'] == 'LONG':
                mfe = max(c[2] for c in future) - entry
                mae = entry - min(c[3] for c in future)
                hit_tp = any(c[2] >= signal['tp'] for c in future)
                hit_sl = any(c[3] <= signal['sl'] for c in future)
            else:
                mfe = entry - min(c[3] for c in future)
                mae = max(c[2] for c in future) - entry
                hit_tp = any(c[3] <= signal['tp'] for c in future)
                hit_sl = any(c[2] >= signal['sl'] for c in future)
            results.append({
                'timestamp': datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(),
                'symbol': symbol,
                'direction': signal['direction'],
                'entry': entry,
                'sl': signal['sl'],
                'tp': signal['tp'],
                'score': signal['score'],
                'stretch': signal['stretch'],
                'context_rsi': signal['context_rsi'],
                'zscore': signal['zscore'],
                'mfe': mfe,
                'mae': mae,
                'hit_tp': hit_tp,
                'hit_sl': hit_sl,
            })
    return results


def bucketize(results, key, buckets):
    lines = [f'===== {key.upper()} BUCKETS =====']
    for low, high in buckets:
        subset = [r for r in results if low <= abs(r.get(key) or 0) < high]
        total = len(subset)
        if total == 0:
            lines.append(f'[{low}, {high}): signals=0')
            continue
        tp_hits = sum(1 for r in subset if r['hit_tp']) / total * 100
        sl_hits = sum(1 for r in subset if r['hit_sl']) / total * 100
        mfe_gt = sum(1 for r in subset if r['mfe'] > r['mae']) / total * 100
        lines.append(f'[{low}, {high}): signals={total} tp_hit_pct={tp_hits:.2f} sl_hit_pct={sl_hits:.2f} mfe_gt_mae_pct={mfe_gt:.2f}')
    lines.append('')
    return lines


def write_outputs(results, scenarios, variants):
    total = len(results)
    tp_hits = sum(1 for r in results if r['hit_tp'])
    sl_hits = sum(1 for r in results if r['hit_sl'])
    avg_mfe = sum(r['mfe'] for r in results) / total if total else 0.0
    avg_mae = sum(r['mae'] for r in results) / total if total else 0.0
    lines = [
        '===== REVERSION SCALP V1 SIGNAL REPLAY =====',
        f'signals: {total}',
        f'hit_tp_pct: {(tp_hits / total * 100) if total else 0:.2f}',
        f'hit_sl_pct: {(sl_hits / total * 100) if total else 0:.2f}',
        f'avg_mfe: {avg_mfe:.6f}',
        f'avg_mae: {avg_mae:.6f}',
        '',
        '===== SCENARIO SCORES =====',
    ]
    for scenario in scenarios:
        hits = sum(1 for row in results if classify_signal(row, scenario))
        lines.append(f'{scenario}: favorable_pct={(hits / total * 100) if total else 0:.2f}')
    lines += ['', '===== FILTER VARIANTS =====']
    for variant in variants:
        subset = [row for row in results if apply_filter_variant(row, variant)]
        subset_total = len(subset)
        lines.append(f'{variant}: signals={subset_total}')
        for scenario in scenarios:
            hits = sum(1 for row in subset if classify_signal(row, scenario))
            lines.append(f'  - {scenario}: favorable_pct={(hits / subset_total * 100) if subset_total else 0:.2f}')
    lines += ['', '===== SIGNALS BY SYMBOL =====']
    by_symbol = {}
    for row in results:
        by_symbol.setdefault(row['symbol'], []).append(row)
    for symbol, rows in by_symbol.items():
        lines.append(
            f"{symbol}: signals={len(rows)} tp_hit_pct={sum(1 for r in rows if r['hit_tp'])/len(rows)*100:.2f} sl_hit_pct={sum(1 for r in rows if r['hit_sl'])/len(rows)*100:.2f} avg_mfe={sum(r['mfe'] for r in rows)/len(rows):.6f} avg_mae={sum(r['mae'] for r in rows)/len(rows):.6f}"
        )
    lines += ['']
    lines += bucketize(results, 'score', [(0.0, 0.55), (0.55, 0.7), (0.7, 1.0), (1.0, 10.0)])
    lines += bucketize(results, 'stretch', [(0.0, 0.0005), (0.0005, 0.001), (0.001, 0.002), (0.002, 1.0)])
    lines += bucketize(results, 'zscore', [(0.0, 0.6), (0.6, 0.8), (0.8, 1.2), (1.2, 10.0)])
    REPORT_PATH.write_text('\n'.join(lines), encoding='utf8')
    with CSV_PATH.open('w', newline='', encoding='utf8') as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()) if results else ['timestamp'])
        writer.writeheader()
        if results:
            writer.writerows(results)
    print(f'Signal replay report generated: {REPORT_PATH}')
    print(f'Signal replay CSV generated: {CSV_PATH}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=30)
    parser.add_argument('--symbol', action='append', dest='symbols')
    parser.add_argument('--lookahead-bars', type=int, default=6)
    parser.add_argument('--scenario', action='append', dest='scenarios')
    parser.add_argument('--variant', action='append', dest='variants')
    args = parser.parse_args()
    scenarios = args.scenarios or ['strict_tp_first', 'strict_sl_first', 'mfe_gt_mae', 'balanced']
    variants = args.variants or ['baseline', 'higher_score', 'deeper_stretch', 'stronger_zscore']
    results = replay(days=args.days, symbols=args.symbols, lookahead_bars=args.lookahead_bars)
    write_outputs(results, scenarios, variants)


if __name__ == '__main__':
    main()
