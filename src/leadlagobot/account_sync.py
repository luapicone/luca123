import aiohttp
from leadlagobot.config.settings import settings


async def fetch_account_snapshot():
    snapshot = {
        'binance': {'status': 'unavailable', 'reason': 'missing_credentials'},
        'bybit': {'status': 'unavailable', 'reason': 'missing_credentials'},
    }

    async with aiohttp.ClientSession() as session:
        if settings.binance_api_key and settings.binance_api_secret:
            snapshot['binance'] = {
                'status': 'dry_run_only',
                'endpoint_hint': '/fapi/v2/account and /fapi/v2/positionRisk',
            }
        if settings.bybit_api_key and settings.bybit_api_secret:
            snapshot['bybit'] = {
                'status': 'dry_run_only',
                'endpoint_hint': '/v5/account/wallet-balance and /v5/position/list',
            }
    return snapshot
