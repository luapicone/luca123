from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode
from leadlagobot.models.types import TickerSnapshot
from leadlagobot.config.settings import settings


AUDIT_LOG = Path('data/execution_dry_run.jsonl')
AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)


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

    def _credentials(self, exchange: str):
        if exchange == 'binance':
            return settings.binance_api_key, settings.binance_api_secret
        if exchange == 'bybit':
            return settings.bybit_api_key, settings.bybit_api_secret
        return '', ''

    def _endpoint_hint(self, exchange: str, side: str):
        if exchange == 'binance':
            return {'exchange': exchange, 'endpoint': '/fapi/v1/order', 'method': 'POST', 'side': side}
        if exchange == 'bybit':
            return {'exchange': exchange, 'endpoint': '/v5/order/create', 'method': 'POST', 'side': side}
        return {'exchange': exchange, 'endpoint': 'unknown', 'method': 'POST', 'side': side}

    def _sign_binance(self, payload: dict, secret: str):
        query = urlencode(payload)
        signature = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        return query + '&signature=' + signature

    def _sign_bybit(self, payload: dict, secret: str):
        body = json.dumps(payload, separators=(',', ':'))
        signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        return signature, body

    def _build_payload(self, intent: ExecutionIntent):
        ts = int(time.time() * 1000)
        if intent.exchange == 'binance':
            return {
                'symbol': intent.symbol,
                'side': intent.side.upper(),
                'type': intent.order_type.upper(),
                'quantity': intent.qty,
                'timestamp': ts,
            }
        if intent.exchange == 'bybit':
            return {
                'category': 'linear',
                'symbol': intent.symbol,
                'side': intent.side.capitalize(),
                'orderType': intent.order_type.capitalize(),
                'qty': str(intent.qty),
                'timeInForce': 'IOC',
            }
        return {'symbol': intent.symbol, 'side': intent.side, 'qty': intent.qty, 'timestamp': ts}

    def _audit(self, payload: dict):
        with AUDIT_LOG.open('a', encoding='utf8') as file:
            file.write(json.dumps(payload) + '\n')

    def _build_placeholder(self, intent: ExecutionIntent):
        api_key, api_secret = self._credentials(intent.exchange)
        payload = self._build_payload(intent)
        if intent.exchange == 'binance' and api_secret:
            signed = self._sign_binance(payload, api_secret)
        elif intent.exchange == 'bybit' and api_secret:
            signature, body = self._sign_bybit(payload, api_secret)
            signed = {'signature': signature, 'body': body}
        else:
            signed = None

        audit = {
            'status': 'dry_run' if settings.dry_run_enabled else 'not_implemented',
            'intent': asdict(intent),
            'endpoint_hint': self._endpoint_hint(intent.exchange, intent.side),
            'payload': payload,
            'signed_preview': signed,
            'has_api_key': bool(api_key),
            'has_api_secret': bool(api_secret),
        }
        self._audit(audit)
        return {
            'status': 'dry_run' if settings.dry_run_enabled else 'not_implemented',
            'reason': 'signed payload prepared but not sent',
            'symbol': intent.symbol,
            'exchange': intent.exchange,
            'side': intent.side,
            'qty': intent.qty,
            'order_type': intent.order_type,
            'reference_price': intent.reference_price,
            'endpoint_hint': self._endpoint_hint(intent.exchange, intent.side),
            'dry_run_enabled': settings.dry_run_enabled,
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
