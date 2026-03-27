import aiohttp
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode
from leadlagobot.config.settings import settings


async def _binance_account_snapshot(session: aiohttp.ClientSession):
    ts = int(time.time() * 1000)
    query = urlencode({'timestamp': ts})
    signature = hmac.new(settings.binance_api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    account_url = f'https://fapi.binance.com/fapi/v2/account?{query}&signature={signature}'
    pos_url = f'https://fapi.binance.com/fapi/v2/positionRisk?{query}&signature={signature}'
    headers = {'X-MBX-APIKEY': settings.binance_api_key}

    async with session.get(account_url, headers=headers) as account_resp:
        account = await account_resp.json()
    async with session.get(pos_url, headers=headers) as pos_resp:
        positions = await pos_resp.json()

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
    }


async def _bybit_account_snapshot(session: aiohttp.ClientSession):
    ts = str(int(time.time() * 1000))
    recv_window = '5000'
    wallet_query = 'accountType=UNIFIED'
    wallet_signature_payload = ts + settings.bybit_api_key + recv_window + wallet_query
    wallet_signature = hmac.new(settings.bybit_api_secret.encode(), wallet_signature_payload.encode(), hashlib.sha256).hexdigest()
    wallet_headers = {
        'X-BAPI-API-KEY': settings.bybit_api_key,
        'X-BAPI-TIMESTAMP': ts,
        'X-BAPI-RECV-WINDOW': recv_window,
        'X-BAPI-SIGN': wallet_signature,
    }

    pos_query = 'category=linear&settleCoin=USDT'
    pos_signature_payload = ts + settings.bybit_api_key + recv_window + pos_query
    pos_signature = hmac.new(settings.bybit_api_secret.encode(), pos_signature_payload.encode(), hashlib.sha256).hexdigest()
    pos_headers = {
        'X-BAPI-API-KEY': settings.bybit_api_key,
        'X-BAPI-TIMESTAMP': ts,
        'X-BAPI-RECV-WINDOW': recv_window,
        'X-BAPI-SIGN': pos_signature,
    }

    async with session.get(f'https://api.bybit.com/v5/account/wallet-balance?{wallet_query}', headers=wallet_headers) as wallet_resp:
        wallet = await wallet_resp.json()
    async with session.get(f'https://api.bybit.com/v5/position/list?{pos_query}', headers=pos_headers) as pos_resp:
        positions = await pos_resp.json()

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
