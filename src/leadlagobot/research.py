from pathlib import Path
import json
from collections import defaultdict

from leadlagobot.utils.atomic_write import atomic_write_text


class SignalResearchStore:
    def __init__(self, signals_path: str = 'data/research_signals.jsonl', summary_path: str = 'data/research_summary.json'):
        self.signals_path = Path(signals_path)
        self.summary_path = Path(summary_path)
        self.signals_path.parent.mkdir(parents=True, exist_ok=True)
        self.summary_path.parent.mkdir(parents=True, exist_ok=True)
        self.samples = defaultdict(list)

    def register(self, symbol: str, payload: dict):
        self.samples[symbol].append(payload)
        with self.signals_path.open('a', encoding='utf8') as file:
            file.write(json.dumps({'symbol': symbol, **payload}) + '\n')

    def flush_summary(self):
        summary = {}
        for symbol, rows in self.samples.items():
            count = len(rows)
            if not count:
                continue
            summary[symbol] = {
                'count': count,
                'avg_gap_pct': sum(r.get('gap_pct', 0.0) for r in rows) / count,
                'avg_quality_score': sum(r.get('quality_score', 0.0) for r in rows) / count,
                'avg_expected_net_edge_pct': sum(r.get('expected_net_edge_pct', 0.0) for r in rows) / count,
                'avg_signal_age_ms': sum(r.get('signal_age_ms', 0.0) for r in rows) / count,
                'confirmed_reversions': sum(1 for r in rows if r.get('reversion_confirmed')),
            }
        atomic_write_text(self.summary_path, json.dumps(summary, indent=2), encoding='utf8')
