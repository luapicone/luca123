from pathlib import Path
import json
from collections import defaultdict
from rich.console import Console
from rich.table import Table

console = Console()
TRADE_LOG = Path('data/paper_trades.jsonl')


def load_trades():
    if not TRADE_LOG.exists():
        return []
    trades = []
    with TRADE_LOG.open('r', encoding='utf8') as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                trades.append(json.loads(line))
            except Exception:
                continue
    return trades


def summarize(trades):
    summary = defaultdict(lambda: {
        'count': 0,
        'net': 0.0,
        'gross': 0.0,
        'fees': 0.0,
        'slippage': 0.0,
        'wins': 0,
        'losses': 0,
        'avg_fill': 0.0,
        'avg_duration_ms': 0.0,
    })
    for trade in trades:
        symbol = trade.get('symbol', 'UNKNOWN')
        bucket = summary[symbol]
        bucket['count'] += 1
        bucket['net'] += trade.get('net_pnl', 0.0)
        bucket['gross'] += trade.get('gross_pnl', 0.0)
        bucket['fees'] += trade.get('fees', 0.0)
        bucket['slippage'] += trade.get('slippage_cost', 0.0)
        bucket['avg_fill'] = ((bucket['avg_fill'] * (bucket['count'] - 1)) + trade.get('fill_ratio', 0.0)) / bucket['count']
        bucket['avg_duration_ms'] = ((bucket['avg_duration_ms'] * (bucket['count'] - 1)) + trade.get('duration_ms', 0.0)) / bucket['count']
        if trade.get('net_pnl', 0.0) >= 0:
            bucket['wins'] += 1
        else:
            bucket['losses'] += 1
    return summary


def main():
    trades = load_trades()
    table = Table(title='LeadLagobot Replay / Backtest Summary', expand=True)
    table.add_column('Symbol')
    table.add_column('Trades', justify='right')
    table.add_column('Wins', justify='right')
    table.add_column('Losses', justify='right')
    table.add_column('Gross', justify='right')
    table.add_column('Fees', justify='right')
    table.add_column('Slip', justify='right')
    table.add_column('Net', justify='right')
    table.add_column('Fill', justify='right')
    table.add_column('Avg ms', justify='right')

    summary = summarize(trades)
    for symbol, row in sorted(summary.items(), key=lambda item: item[1]['net'], reverse=True):
        table.add_row(
            symbol,
            str(row['count']),
            str(row['wins']),
            str(row['losses']),
            f"{row['gross']:.2f}",
            f"{row['fees']:.2f}",
            f"{row['slippage']:.2f}",
            f"{row['net']:.2f}",
            f"{row['avg_fill']:.2f}",
            f"{row['avg_duration_ms']:.0f}",
        )

    console.print(table)


if __name__ == '__main__':
    main()
