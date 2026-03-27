from dataclasses import dataclass
from leadlagobot.models.types import TickerSnapshot


@dataclass
class ExecutionIntent:
    symbol: str
    side: str
    qty: float
    reference_price: float
    exchange: str


class ExecutionAdapter:
    def place_entry(self, intent: ExecutionIntent, tick: TickerSnapshot):
        raise NotImplementedError

    def place_exit(self, intent: ExecutionIntent, tick: TickerSnapshot):
        raise NotImplementedError


class PaperExecutionAdapter(ExecutionAdapter):
    def place_entry(self, intent: ExecutionIntent, tick: TickerSnapshot):
        return {
            'status': 'paper_filled',
            'symbol': intent.symbol,
            'side': intent.side,
            'qty': intent.qty,
            'exchange': intent.exchange,
            'reference_price': intent.reference_price,
        }

    def place_exit(self, intent: ExecutionIntent, tick: TickerSnapshot):
        return {
            'status': 'paper_filled',
            'symbol': intent.symbol,
            'side': intent.side,
            'qty': intent.qty,
            'exchange': intent.exchange,
            'reference_price': intent.reference_price,
        }


class RealExecutionAdapter(ExecutionAdapter):
    def place_entry(self, intent: ExecutionIntent, tick: TickerSnapshot):
        return {
            'status': 'not_implemented',
            'reason': 'real execution adapter pending',
            'symbol': intent.symbol,
            'exchange': intent.exchange,
        }

    def place_exit(self, intent: ExecutionIntent, tick: TickerSnapshot):
        return {
            'status': 'not_implemented',
            'reason': 'real execution adapter pending',
            'symbol': intent.symbol,
            'exchange': intent.exchange,
        }
