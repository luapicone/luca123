from collections import defaultdict
from pathlib import Path
import json

from leadlagobot.config.settings import settings


class PairMetricsTracker:
    def __init__(self, path: str = 'data/pair_metrics.json', rejected_path: str = 'data/rejected_opportunities.jsonl', ranking_path: str = 'data/pair_ranking.json', cancelled_path: str = 'data/cancelled_orders.jsonl'):
        self.path = Path(path)
        self.rejected_path = Path(rejected_path)
        self.ranking_path = Path(ranking_path)
        self.cancelled_path = Path(cancelled_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.rejected_path.parent.mkdir(parents=True, exist_ok=True)
        self.ranking_path.parent.mkdir(parents=True, exist_ok=True)
        self.cancelled_path.parent.mkdir(parents=True, exist_ok=True)
        self.data = defaultdict(lambda: {
            'signals': 0,
            'opens': 0,
            'closes': 0,
            'wins': 0,
            'losses': 0,
            'rejected': 0,
            'cancelled': 0,
            'gross_pnl': 0.0,
            'net_pnl': 0.0,
            'avg_entry_gap_pct': 0.0,
            'avg_exit_gap_pct': 0.0,
            'avg_duration_ms': 0.0,
            'avg_signal_age_ms': 0.0,
            'avg_quality_score': 0.0,
            'avg_fill_ratio': 0.0,
            'ranking_score': 0.0,
        })

    def _update_avg(self, current: float, count: int, new_value: float) -> float:
        if count <= 1:
            return new_value
        return ((current * (count - 1)) + new_value) / count

    def _recalculate_ranking(self, symbol: str):
        bucket = self.data[symbol]
        win_rate = (bucket['wins'] / bucket['closes']) if bucket['closes'] else 0.0
        rejection_penalty = (bucket['rejected'] / bucket['signals']) if bucket['signals'] else 0.0
        cancel_penalty = (bucket['cancelled'] / bucket['signals']) if bucket['signals'] else 0.0
        bucket['ranking_score'] = (
            (bucket['net_pnl'] * settings.ranking_weight_net_pnl)
            + (bucket['avg_quality_score'] * settings.ranking_weight_quality)
            + (bucket['avg_fill_ratio'] * settings.ranking_weight_fill)
            + (win_rate * settings.ranking_weight_win_rate)
            - (bucket['avg_signal_age_ms'] / 1000)
            - (rejection_penalty * 20)
            - (cancel_penalty * 25)
        )

    def register_signal(self, symbol: str, signal_age_ms: float, quality_score: float):
        bucket = self.data[symbol]
        bucket['signals'] += 1
        bucket['avg_signal_age_ms'] = self._update_avg(bucket['avg_signal_age_ms'], bucket['signals'], signal_age_ms)
        bucket['avg_quality_score'] = self._update_avg(bucket['avg_quality_score'], bucket['signals'], quality_score)
        self._recalculate_ranking(symbol)

    def register_rejected(self, symbol: str, gap_pct: float, quality_score: float, signal_age_ms: float, reason: str):
        bucket = self.data[symbol]
        bucket['rejected'] += 1
        self._recalculate_ranking(symbol)
        with self.rejected_path.open('a', encoding='utf8') as file:
            file.write(json.dumps({
                'symbol': symbol,
                'gap_pct': gap_pct,
                'quality_score': quality_score,
                'signal_age_ms': signal_age_ms,
                'reason': reason,
            }) + '\n')

    def register_cancelled(self, symbol: str, side: str, reason: str, fill_ratio: float):
        bucket = self.data[symbol]
        bucket['cancelled'] += 1
        count = max(bucket['opens'] + bucket['closes'] + bucket['cancelled'], 1)
        bucket['avg_fill_ratio'] = self._update_avg(bucket['avg_fill_ratio'], count, fill_ratio)
        self._recalculate_ranking(symbol)
        with self.cancelled_path.open('a', encoding='utf8') as file:
            file.write(json.dumps({
                'symbol': symbol,
                'side': side,
                'reason': reason,
                'fill_ratio': fill_ratio,
            }) + '\n')

    def register_open(self, symbol: str, entry_gap_pct: float, fill_ratio: float):
        bucket = self.data[symbol]
        bucket['opens'] += 1
        bucket['avg_entry_gap_pct'] = self._update_avg(bucket['avg_entry_gap_pct'], bucket['opens'], entry_gap_pct)
        bucket['avg_fill_ratio'] = self._update_avg(bucket['avg_fill_ratio'], bucket['opens'], fill_ratio)
        self._recalculate_ranking(symbol)

    def register_close(self, trade):
        bucket = self.data[trade.symbol]
        bucket['closes'] += 1
        bucket['gross_pnl'] += trade.gross_pnl
        bucket['net_pnl'] += trade.net_pnl
        bucket['avg_exit_gap_pct'] = self._update_avg(bucket['avg_exit_gap_pct'], bucket['closes'], trade.exit_gap_pct)
        bucket['avg_duration_ms'] = self._update_avg(bucket['avg_duration_ms'], bucket['closes'], trade.duration_ms)
        bucket['avg_fill_ratio'] = self._update_avg(bucket['avg_fill_ratio'], bucket['closes'], trade.fill_ratio)
        if trade.net_pnl >= 0:
            bucket['wins'] += 1
        else:
            bucket['losses'] += 1
        self._recalculate_ranking(trade.symbol)

    def get_top_symbols(self) -> set[str]:
        ranking = sorted(
            (
                (symbol, values)
                for symbol, values in self.data.items()
                if values['signals'] >= settings.ranking_min_signals
            ),
            key=lambda item: item[1]['ranking_score'],
            reverse=True,
        )
        return {symbol for symbol, _ in ranking[: settings.top_pairs_limit]}

    def flush(self):
        serializable = {symbol: values for symbol, values in self.data.items()}
        self.path.write_text(json.dumps(serializable, indent=2), encoding='utf8')

        ranking = sorted(
            ({'symbol': symbol, **values} for symbol, values in serializable.items()),
            key=lambda item: item['ranking_score'],
            reverse=True,
        )
        self.ranking_path.write_text(json.dumps(ranking, indent=2), encoding='utf8')
