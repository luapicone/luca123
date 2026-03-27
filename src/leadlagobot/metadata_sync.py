import asyncio
from leadlagobot.contracts import update_rules
from leadlagobot.exchange_metadata import fetch_binance_metadata, fetch_bybit_metadata
from leadlagobot.config.settings import settings


async def main():
    binance = await fetch_binance_metadata(settings.symbols)
    bybit = await fetch_bybit_metadata(settings.symbols)
    merged = {**binance, **bybit}
    update_rules(merged)
    print(f'Metadata synced for {len(merged)} symbols')


if __name__ == '__main__':
    asyncio.run(main())
