import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / 'data' / 'research_summary.json'
OUT_PATH = ROOT / 'research_report.txt'


def main():
    if not SUMMARY_PATH.exists():
        print('No existe data/research_summary.json')
        return

    summary = json.loads(SUMMARY_PATH.read_text())
    ranked = sorted(summary.items(), key=lambda item: item[1].get('avg_expected_net_edge_pct', 0.0), reverse=True)

    lines = []
    lines.append('===== RESEARCH REPORT =====')
    lines.append(f'total_symbols: {len(ranked)}')
    lines.append('')
    for symbol, row in ranked:
        lines.append(f'{symbol}: {row}')

    OUT_PATH.write_text('\n'.join(lines), encoding='utf8')
    print(f'Reporte generado: {OUT_PATH}')


if __name__ == '__main__':
    main()
