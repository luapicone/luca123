from pathlib import Path
import json
from leadlagobot.models.types import TickerSnapshot


class ReconciliationStore:
    def __init__(self, path: str = 'data/reconciliation.json'):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write_snapshot(self, open_positions: dict, latest_ticks: dict[str, dict[str, TickerSnapshot]], account_snapshot: dict | None = None):
        payload = {
            'open_positions': {
                symbol: {
                    'qty': position.qty,
                    'requested_qty': position.requested_qty,
                    'fill_ratio': position.fill_ratio,
                    'entry_price': position.follower_entry_price,
                    'leader_price': position.leader_price,
                }
                for symbol, position in open_positions.items()
            },
            'latest_ticks': {
                symbol: {
                    exchange: {
                        'price': tick.price,
                        'bid': tick.bid,
                        'ask': tick.ask,
                        'bid_size': tick.bid_size,
                        'ask_size': tick.ask_size,
                        'ts': tick.ts,
                    }
                    for exchange, tick in exchanges.items()
                }
                for symbol, exchanges in latest_ticks.items()
            },
            'account_snapshot': account_snapshot or {},
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding='utf8')
