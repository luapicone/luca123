from dataclasses import dataclass
import aiohttp


@dataclass
class SymbolMetadata:
    symbol: str
    tick_size: float
    qty_step: float
    min_qty: float
    min_notional: float


async def fetch_binance_metadata(symbols: list[str]) -> dict[str, SymbolMetadata]:
    url = 'https://fapi.binance.com/fapi/v1/exchangeInfo'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
    result = {}
    wanted = set(symbols)
    for item in data.get('symbols', []):
        symbol = item.get('symbol')
        if symbol not in wanted:
            continue
        filters = {f['filterType']: f for f in item.get('filters', [])}
        price_filter = filters.get('PRICE_FILTER', {})
        lot_filter = filters.get('LOT_SIZE', {})
        notional_filter = filters.get('MIN_NOTIONAL', {})
        result[symbol] = SymbolMetadata(
            symbol=symbol,
            tick_size=float(price_filter.get('tickSize', 0.0001)),
            qty_step=float(lot_filter.get('stepSize', 0.001)),
            min_qty=float(lot_filter.get('minQty', 0.001)),
            min_notional=float(notional_filter.get('notional', 5.0)),
        )
    return result


async def fetch_bybit_metadata(symbols: list[str]) -> dict[str, SymbolMetadata]:
    url = 'https://api.bybit.com/v5/market/instruments-info?category=linear'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
    result = {}
    wanted = set(symbols)
    for item in data.get('result', {}).get('list', []):
        symbol = item.get('symbol')
        if symbol not in wanted:
            continue
        lot = item.get('lotSizeFilter', {})
        price = item.get('priceFilter', {})
        result[symbol] = SymbolMetadata(
            symbol=symbol,
            tick_size=float(price.get('tickSize', 0.0001)),
            qty_step=float(lot.get('qtyStep', 0.001)),
            min_qty=float(lot.get('minOrderQty', 0.001)),
            min_notional=float(lot.get('minNotionalValue', 5.0)),
        )
    return result
