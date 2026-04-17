from pprint import pprint

import ccxt

from reversion_scalp_v1_aggressive.config import EXCHANGE_ID
from reversion_scalp_v1_aggressive.live_config import load_live_settings, validate_live_settings


def main():
    settings = load_live_settings()
    ok, reason = validate_live_settings(settings)
    if not ok:
        print({'ok': False, 'reason': reason})
        return
    if not settings.enabled:
        print({'ok': True, 'reason': 'live_trading_disabled', 'note': 'connection test skipped because LIVE_TRADING=false'})
        return

    exchange = getattr(ccxt, EXCHANGE_ID)({
        'enableRateLimit': True,
        'apiKey': settings.api_key,
        'secret': settings.api_secret,
        'options': {'defaultType': 'future'},
    })

    balance = exchange.fetch_balance()
    futures_usdt = balance.get('USDT', {})
    result = {
        'ok': True,
        'exchange': EXCHANGE_ID,
        'live_trading': settings.enabled,
        'max_live_concurrent_trades': settings.max_live_concurrent_trades,
        'max_live_symbol_notional': settings.max_live_symbol_notional,
        'usdt_balance': futures_usdt,
    }
    pprint(result)


if __name__ == '__main__':
    main()
