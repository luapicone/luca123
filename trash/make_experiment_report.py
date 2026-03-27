import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / 'experiments' / 'summary.json'
OUT_PATH = ROOT / 'experiment_report.txt'


def score(summary: dict) -> float:
    return (
        summary.get('total_net_pnl', 0.0) * 12
        + summary.get('win_rate_pct', 0.0)
        + summary.get('avg_fill_ratio', 0.0) * 20
        + summary.get('avg_realized_net_edge_pct', 0.0) * 15
        - summary.get('cancellations', 0) * 0.5
        - summary.get('rejections', 0) * 0.0003
    )


def main():
    if not SUMMARY_PATH.exists():
        print('No existe experiments/summary.json')
        return

    summaries = json.loads(SUMMARY_PATH.read_text())
    ranked = sorted(summaries, key=score, reverse=True)

    lines = []
    lines.append('===== EXPERIMENT REPORT =====')
    lines.append(f'total_experiments: {len(ranked)}')
    lines.append('')

    for item in ranked:
        lines.append(f"name: {item.get('name')}")
        lines.append(f"score: {round(score(item), 6)}")
        lines.append(f"trades: {item.get('trades')}")
        lines.append(f"wins: {item.get('wins')}")
        lines.append(f"losses: {item.get('losses')}")
        lines.append(f"win_rate_pct: {round(item.get('win_rate_pct', 0.0), 4)}")
        lines.append(f"total_net_pnl: {round(item.get('total_net_pnl', 0.0), 6)}")
        lines.append(f"total_gross_pnl: {round(item.get('total_gross_pnl', 0.0), 6)}")
        lines.append(f"avg_fill_ratio: {round(item.get('avg_fill_ratio', 0.0), 6)}")
        lines.append(f"avg_expected_net_edge_pct: {round(item.get('avg_expected_net_edge_pct', 0.0), 6)}")
        lines.append(f"avg_realized_net_edge_pct: {round(item.get('avg_realized_net_edge_pct', 0.0), 6)}")
        lines.append(f"rejections: {item.get('rejections')}")
        lines.append(f"cancellations: {item.get('cancellations')}")
        lines.append(f"env: {item.get('env')}")
        lines.append(f"top_ranking: {item.get('top_ranking', [])[:5]}")
        lines.append('')

    OUT_PATH.write_text('\n'.join(lines), encoding='utf8')
    print(f'Reporte generado: {OUT_PATH}')


if __name__ == '__main__':
    main()
