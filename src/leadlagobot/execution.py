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
    order_type: str = 'market'


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
            'order_type': intent.order_type,
        }

    def place_exit(self, intent: ExecutionIntent, tick: TickerSnapshot):
        return {
            'status': 'paper_filled',
            'symbol': intent.symbol,
            'side': intent.side,
            'qty': intent.qty,
            'exchange': intent.exchange,
            'reference_price': intent.reference_price,
            'order_type': intent.order_type,
        }


class RealExecutionAdapter(ExecutionAdapter):
    def _guard(self):
        if not settings.real_execution_enabled:
            return {
                'status': 'blocked',
                'reason': 'real execution disabled; set REAL_EXECUTION_ENABLED=true explicitly',
            }
        return None

    def _endpoint_hint(self, exchange: str, side: str):
        if exchange == 'binance':
            return {'exchange': exchange, 'endpoint': '/fapi/v1/order', 'method': 'POST', 'side': side}
        if exchange == 'bybit':
            return {'exchange': exchange, 'endpoint': '/v5/order/create', 'method': 'POST', 'side': side}
        return {'exchange': exchange, 'endpoint': 'unknown', 'method': 'POST', 'side': side}

    def _build_placeholder(self, intent: ExecutionIntent):
        return {
            'status': 'not_implemented',
            'reason': 'real execution adapter pending signed API wiring',
            'symbol': intent.symbol,
            'exchange': intent.exchange,
            'side': intent.side,
            'qty': intent.qty,
            'order_type': intent.order_type,
            'reference_price': intent.reference_price,
            'endpoint_hint': self._endpoint_hint(intent.exchange, intent.side),
        }

    def place_entry(self, intent: ExecutionIntent, tick: TickerSnapshot):
        blocked = self._guard()
        if blocked:
            return blocked | {
                'symbol': intent.symbol,
                'exchange': intent.exchange,
                'side': intent.side,
                'qty': intent.qty,
            }
        return self._build_placeholder(intent)

    def place_exit(self, intent: ExecutionIntent, tick: TickerSnapshot):
        blocked = self._guard()
        if blocked:
            return blocked | {
                'symbol': intent.symbol,
                'exchange': intent.exchange,
                'side': intent.side,
                'qty': intent.qty,
            }
        return self._build_placeholder(intent)
