import csv
from pathlib import Path

DATA_DIR = Path('tick_vampire_v3/data')
SIGNALS_CSV = DATA_DIR / 'signals.csv'
RESEARCH_REPORT = Path('tick_vampire_v3_research_report.txt')

HEADER = [
    'timestamp', 'symbol', 'direction', 'reason', 'score', 'price', 'rsi', 'volume', 'volume_ma',
    'spread', 'outcome_reason', 'pnl', 'fee', 'bars_held'
]


def ensure_store():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SIGNALS_CSV.exists():
        with SIGNALS_CSV.open('w', newline='', encoding='utf8') as f:
            writer = csv.writer(f)
            writer.writerow(HEADER)


def append_signal(row: dict):
    ensure_store()
    with SIGNALS_CSV.open('a', newline='', encoding='utf8') as f:
        writer = csv.writer(f)
        writer.writerow([row.get(k, '') for k in HEADER])


def _load_rows():
    if not SIGNALS_CSV.exists():
        return []
    with SIGNALS_CSV.open('r', encoding='utf8') as f:
        reader = csv.DictReader(f)
        return list(reader)


def build_report():
    rows = _load_rows()
    lines = ['===== TICK VAMPIRE v3 RESEARCH REPORT =====']
    lines.append(f'signal_rows: {len(rows)}')
    if not rows:
        lines.append('no research rows yet')
        RESEARCH_REPORT.write_text('\n'.join(lines), encoding='utf8')
        return RESEARCH_REPORT

    def as_float(v):
        try:
            return float(v)
        except Exception:
            return 0.0

    total_pnl = sum(as_float(r['pnl']) for r in rows)
    wins = sum(1 for r in rows if as_float(r['pnl']) > 0)
    losses = sum(1 for r in rows if as_float(r['pnl']) <= 0)
    wr = (wins / len(rows) * 100) if rows else 0.0
    lines += [
        f'wins: {wins}',
        f'losses: {losses}',
        f'win_rate_pct: {wr:.4f}',
        f'total_pnl: {total_pnl:.6f}',
        f'avg_pnl: {(total_pnl / len(rows)):.6f}',
        '',
        '===== BY SYMBOL =====',
    ]

    symbols = sorted(set(r['symbol'] for r in rows))
    for symbol in symbols:
        chunk = [r for r in rows if r['symbol'] == symbol]
        pnl = sum(as_float(r['pnl']) for r in chunk)
        w = sum(1 for r in chunk if as_float(r['pnl']) > 0)
        lines.append(f'{symbol}: trades={len(chunk)} wins={w} pnl={pnl:.6f} avg={(pnl / len(chunk)):.6f}')

    lines += ['', '===== BY DIRECTION =====']
    for direction in ['LONG', 'SHORT']:
        chunk = [r for r in rows if r['direction'] == direction]
        if not chunk:
            continue
        pnl = sum(as_float(r['pnl']) for r in chunk)
        w = sum(1 for r in chunk if as_float(r['pnl']) > 0)
        lines.append(f'{direction}: trades={len(chunk)} wins={w} pnl={pnl:.6f} avg={(pnl / len(chunk)):.6f}')

    lines += ['', '===== BY EXIT REASON =====']
    reasons = sorted(set(r['outcome_reason'] for r in rows))
    for reason in reasons:
        chunk = [r for r in rows if r['outcome_reason'] == reason]
        pnl = sum(as_float(r['pnl']) for r in chunk)
        lines.append(f'{reason}: trades={len(chunk)} pnl={pnl:.6f} avg={(pnl / len(chunk)):.6f}')

    lines += ['', '===== SCORE BUCKETS =====']
    buckets = [(2.0, 2.5), (2.5, 3.0), (3.0, 4.0), (4.0, 99.0)]
    for lo, hi in buckets:
        chunk = [r for r in rows if lo <= as_float(r['score']) < hi]
        if not chunk:
            lines.append(f'{lo:.1f}-{hi:.1f}: trades=0')
            continue
        pnl = sum(as_float(r['pnl']) for r in chunk)
        w = sum(1 for r in chunk if as_float(r['pnl']) > 0)
        lines.append(f'{lo:.1f}-{hi:.1f}: trades={len(chunk)} wins={w} pnl={pnl:.6f} avg={(pnl / len(chunk)):.6f}')

    RESEARCH_REPORT.write_text('\n'.join(lines), encoding='utf8')
    return RESEARCH_REPORT
