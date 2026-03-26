from collections import defaultdict
from pathlib import Path
import json


class PairMetricsTracker:
    def __init__(self, path: str = 'data/pair_metrics.json'):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = defaultdict(lambda: {
            'signals': 0,
            'opens': 0,
            'closes': 0,
            'wins': 0,
            'losses': 0,
            'gross_pnl': 0.0,
            'net_pnl': 0.0,
            'avg_entry_gap_pct': 0.0,
            'avg_exit_gap_pct': 0.0,
            'avg_duration_ms': 0.0,
            'avg_signal_age_ms': 0.0,
            'avg_quality_score': 0.0,
        })

    def _update_avg(self, current: float, count: int, new_value: float) -> float:
        if count <= 1:
            return new_value
        return ((current * (count - 1)) + new_value) / count

    def register_signal(self, symbol: str, signal_age_ms: float, quality_score: float):
        bucket = self.data[symbol]
        bucket['signals'] += 1
        bucket['avg_signal_age_ms'] = self._update_avg(bucket['avg_signal_age_ms'], bucket['signals'], signal_age_ms)
        bucket['avg_quality_score'] = self._update_avg(bucket['avg_quality_score'], bucket['signals'], quality_score)

    def register_open(self, symbol: str, entry_gap_pct: float):
        bucket = self.data[symbol]
        bucket['opens'] += 1
        bucket['avg_entry_gap_pct'] = self._update_avg(bucket['avg_entry_gap_pct'], bucket['opens'], entry_gap_pct)

    def register_close(self, trade):
        bucket = self.data[trade.symbol]
        bucket['closes'] += 1
        bucket['gross_pnl'] += trade.gross_pnl
        bucket['net_pnl'] += trade.net_pnl
        bucket['avg_exit_gap_pct'] = self._update_avg(bucket['avg_exit_gap_pct'], bucket['closes'], trade.exit_gap_pct)
        bucket['avg_duration_ms'] = self._update_avg(bucket['avg_duration_ms'], bucket['closes'], trade.duration_ms)
        if trade.net_pnl >= 0:
            bucket['wins'] += 1
        else:
            bucket['losses'] += 1

    def flush(self):
        serializable = {symbol: values for symbol, values in self.data.items()}
        self.path.write_text(json.dumps(serializable, indent=2), encoding='utf8')
