from pathlib import Path
import json
import time
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel

console = Console()
DATA_DIR = Path('data')


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf8'))
    except Exception:
        return default


def build_layout():
    status = load_json(DATA_DIR / 'status.json', {})
    ranking = load_json(DATA_DIR / 'pair_ranking.json', [])
    metrics = load_json(DATA_DIR / 'pair_metrics.json', {})

    status_lines = [
        f"Balance: {status.get('balance', 0):.2f}",
        f"Tracked: {status.get('tracked_symbol', '-')}",
        f"Open positions: {', '.join(status.get('open_positions', [])) or '-'}",
        f"Top symbols: {', '.join(status.get('top_symbols', [])) or '-'}",
        f"Latest gap: {status.get('latest_gap_pct', 0):.4f}%",
        f"Latest quality: {status.get('latest_quality_score', 0):.4f}",
        f"Latest signal age: {status.get('latest_signal_age_ms', 0):.0f} ms",
    ]
    panel = Panel('\n'.join(status_lines), title='LeadLagobot Status')

    ranking_table = Table(title='Top Ranking', expand=True)
    ranking_table.add_column('Symbol')
    ranking_table.add_column('Score', justify='right')
    ranking_table.add_column('Net PnL', justify='right')
    ranking_table.add_column('Signals', justify='right')
    ranking_table.add_column('Avg Q', justify='right')

    for row in ranking[:10]:
        ranking_table.add_row(
            row.get('symbol', '-'),
            f"{row.get('ranking_score', 0):.2f}",
            f"{row.get('net_pnl', 0):.2f}",
            str(row.get('signals', 0)),
            f"{row.get('avg_quality_score', 0):.3f}",
        )

    metrics_table = Table(title='Metrics Snapshot', expand=True)
    metrics_table.add_column('Symbol')
    metrics_table.add_column('Wins', justify='right')
    metrics_table.add_column('Losses', justify='right')
    metrics_table.add_column('Rejected', justify='right')
    metrics_table.add_column('Cancelled', justify='right')
    metrics_table.add_column('Fill', justify='right')

    for symbol, row in list(metrics.items())[:10]:
        metrics_table.add_row(
            symbol,
            str(row.get('wins', 0)),
            str(row.get('losses', 0)),
            str(row.get('rejected', 0)),
            str(row.get('cancelled', 0)),
            f"{row.get('avg_fill_ratio', 0):.2f}",
        )

    return Panel.fit(ranking_table), panel, Panel.fit(metrics_table)


def main():
    with Live(console=console, refresh_per_second=1) as live:
        while True:
            ranking_panel, status_panel, metrics_panel = build_layout()
            live.update(Panel(f"\n{status_panel}\n\n{ranking_panel}\n\n{metrics_panel}", title='LeadLagobot Dashboard'))
            time.sleep(1)


if __name__ == '__main__':
    main()
