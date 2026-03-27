from dataclasses import dataclass
from leadlagobot.models.types import TickerSnapshot
from leadlagobot.config.settings import settings


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
    def _guard(self):
        if not settings.real_execution_enabled:
            return {
                'status': 'blocked',
                'reason': 'real execution disabled; set REAL_EXECUTION_ENABLED=true explicitly',
            }
        return None

    def place_entry(self, intent: ExecutionIntent, tick: TickerSnapshot):
        blocked = self._guard()
        if blocked:
            return blocked | {
                'symbol': intent.symbol,
                'exchange': intent.exchange,
                'side': intent.side,
            }
        return {
            'status': 'not_implemented',
            'reason': 'real execution adapter pending exchange wiring',
            'symbol': intent.symbol,
            'exchange': intent.exchange,
            'side': intent.side,
        }

    def place_exit(self, intent: ExecutionIntent, tick: TickerSnapshot):
        blocked = self._guard()
        if blocked:
            return blocked | {
                'symbol': intent.symbol,
                'exchange': intent.exchange,
                'side': intent.side,
            }
        return {
            'status': 'not_implemented',
            'reason': 'real execution adapter pending exchange wiring',
            'symbol': intent.symbol,
            'exchange': intent.exchange,
            'side': intent.side,
        }
