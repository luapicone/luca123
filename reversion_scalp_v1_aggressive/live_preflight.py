from pprint import pprint

import ccxt

from reversion_scalp_v1_aggressive.config import EXCHANGE_ID, SYMBOLS
from reversion_scalp_v1_aggressive.live_config import load_live_settings, validate_live_settings


def extract_symbol_constraints(market: dict):
    limits = market.get('limits', {})
    amount = limits.get('amount', {}) or {}
    cost = limits.get('cost', {}) or {}
    precision = market.get('precision', {}) or {}
    return {
        'symbol': market.get('symbol'),
        'active': market.get('active'),
        'contract': market.get('contract'),
        'linear': market.get('linear'),
        'min_amount': amount.get('min'),
        'min_cost': cost.get('min'),
        'amount_precision': precision.get('amount'),
        'price_precision': precision.get('price'),
    }


def main():
    settings = load_live_settings()
    ok, reason = validate_live_settings(settings)
    if not ok:
        print({'ok': False, 'reason': reason})
        return
    if not settings.enabled:
        print({'ok': False, 'reason': 'live_trading_disabled'})
        return

    exchange = getattr(ccxt, EXCHANGE_ID)({
        'enableRateLimit': True,
        'apiKey': settings.api_key,
        'secret': settings.api_secret,
        'options': {'defaultType': 'future'},
    })

    markets = exchange.load_markets()
    balance = exchange.fetch_balance()
    usdt_balance = balance.get('USDT', {})

    checked_symbols = []
    unsupported_symbols = []
    for symbol in SYMBOLS:
        market = markets.get(symbol)
        if not market:
            unsupported_symbols.append(symbol)
            continue
        checked_symbols.append(extract_symbol_constraints(market))

    result = {
        'ok': True,
        'exchange': EXCHANGE_ID,
        'live_trading': settings.enabled,
        'max_live_concurrent_trades': settings.max_live_concurrent_trades,
        'max_live_symbol_notional': settings.max_live_symbol_notional,
        'usdt_balance': usdt_balance,
        'supported_symbols_checked': checked_symbols,
        'unsupported_symbols': unsupported_symbols,
        'note': 'preflight only, no live orders were sent',
    }
    pprint(result)


if __name__ == '__main__':
    main()
