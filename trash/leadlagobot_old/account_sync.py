import aiohttp
import hashlib
import hmac
import time
from urllib.parse import urlencode
from leadlagobot.config.settings import settings


async def _binance_signed_get(session: aiohttp.ClientSession, path: str, query_dict: dict):
    ts_query = {**query_dict, 'timestamp': int(time.time() * 1000)}
    query = urlencode(ts_query)
    signature = hmac.new(settings.binance_api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    url = f'https://fapi.binance.com{path}?{query}&signature={signature}'
    headers = {'X-MBX-APIKEY': settings.binance_api_key}
    async with session.get(url, headers=headers) as response:
        return await response.json()


async def _bybit_signed_get(session: aiohttp.ClientSession, path: str, query: str):
    ts = str(int(time.time() * 1000))
    recv_window = '5000'
    signature_payload = ts + settings.bybit_api_key + recv_window + query
    signature = hmac.new(settings.bybit_api_secret.encode(), signature_payload.encode(), hashlib.sha256).hexdigest()
    headers = {
        'X-BAPI-API-KEY': settings.bybit_api_key,
        'X-BAPI-TIMESTAMP': ts,
        'X-BAPI-RECV-WINDOW': recv_window,
        'X-BAPI-SIGN': signature,
    }
    async with session.get(f'https://api.bybit.com{path}?{query}', headers=headers) as response:
        return await response.json()


async def _binance_account_snapshot(session: aiohttp.ClientSession):
    account = await _binance_signed_get(session, '/fapi/v2/account', {})
    positions = await _binance_signed_get(session, '/fapi/v2/positionRisk', {})
    orders = await _binance_signed_get(session, '/fapi/v1/openOrders', {})

    return {
        'status': 'ok',
        'wallet_balance': account.get('totalWalletBalance'),
        'available_balance': account.get('availableBalance'),
        'positions': [
            {
                'symbol': item.get('symbol'),
                'positionAmt': item.get('positionAmt'),
                'entryPrice': item.get('entryPrice'),
                'unRealizedProfit': item.get('unRealizedProfit'),
            }
            for item in positions if str(item.get('positionAmt', '0')) not in ('0', '0.0')
        ],
        'open_orders': [
            {
                'symbol': item.get('symbol'),
                'orderId': item.get('orderId'),
                'status': item.get('status'),
                'origQty': item.get('origQty'),
                'executedQty': item.get('executedQty'),
            }
            for item in orders
        ],
    }


async def _bybit_account_snapshot(session: aiohttp.ClientSession):
    wallet = await _bybit_signed_get(session, '/v5/account/wallet-balance', 'accountType=UNIFIED')
    positions = await _bybit_signed_get(session, '/v5/position/list', 'category=linear&settleCoin=USDT')
    orders = await _bybit_signed_get(session, '/v5/order/realtime', 'category=linear&settleCoin=USDT')

    accounts = wallet.get('result', {}).get('list', [])
    first = accounts[0] if accounts else {}
    coins = first.get('coin', []) if isinstance(first, dict) else []
    usdt = next((coin for coin in coins if coin.get('coin') == 'USDT'), {})

    return {
        'status': 'ok',
        'wallet_balance': usdt.get('walletBalance'),
        'available_balance': usdt.get('availableToWithdraw'),
        'positions': [
            {
                'symbol': item.get('symbol'),
                'size': item.get('size'),
                'avgPrice': item.get('avgPrice'),
                'unrealisedPnl': item.get('unrealisedPnl'),
            }
            for item in positions.get('result', {}).get('list', []) if str(item.get('size', '0')) not in ('0', '0.0', '')
        ],
        'open_orders': [
            {
                'symbol': item.get('symbol'),
                'orderId': item.get('orderId'),
                'orderStatus': item.get('orderStatus'),
                'qty': item.get('qty'),
                'cumExecQty': item.get('cumExecQty'),
            }
            for item in orders.get('result', {}).get('list', [])
        ],
    }


async def fetch_account_snapshot():
    snapshot = {
        'binance': {'status': 'unavailable', 'reason': 'missing_credentials'},
        'bybit': {'status': 'unavailable', 'reason': 'missing_credentials'},
    }

    async with aiohttp.ClientSession() as session:
        if settings.binance_api_key and settings.binance_api_secret:
            try:
                snapshot['binance'] = await _binance_account_snapshot(session)
            except Exception as exc:
                snapshot['binance'] = {'status': 'error', 'reason': str(exc)}
        if settings.bybit_api_key and settings.bybit_api_secret:
            try:
                snapshot['bybit'] = await _bybit_account_snapshot(session)
            except Exception as exc:
                snapshot['bybit'] = {'status': 'error', 'reason': str(exc)}
    return snapshot
