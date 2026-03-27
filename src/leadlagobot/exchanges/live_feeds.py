import asyncio
import json
import aiohttp
from leadlagobot.models.types import TickerSnapshot


class BinanceTickerFeed:
    def __init__(self, symbols: list[str], queue: asyncio.Queue):
        self.symbols = [symbol.lower() for symbol in symbols]
        self.queue = queue

    async def run(self):
        stream_names = '/'.join(f'{symbol}@bookTicker/{symbol}@depth5@100ms' for symbol in self.symbols)
        url = f'wss://fstream.binance.com/stream?streams={stream_names}'
        state: dict[str, dict] = {}

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url, heartbeat=20) as ws:
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    payload = json.loads(msg.data)
                    stream = payload.get('stream', '')
                    data = payload.get('data', {})
                    symbol = data.get('s')
                    if not symbol:
                        continue

                    bucket = state.setdefault(symbol, {})
                    if '@bookTicker' in stream:
                        bucket['bid'] = float(data['b'])
                        bucket['ask'] = float(data['a'])
                        bucket['bid_size'] = float(data['B'])
                        bucket['ask_size'] = float(data['A'])
                        bucket['ts'] = (data.get('E') or 0) / 1000
                    elif '@depth5' in stream:
                        bucket['bid_levels'] = [(float(price), float(size)) for price, size in data.get('b', [])]
                        bucket['ask_levels'] = [(float(price), float(size)) for price, size in data.get('a', [])]
                        bucket['ts'] = (data.get('E') or 0) / 1000

                    if 'bid' in bucket and 'ask' in bucket:
                        await self.queue.put(
                            TickerSnapshot(
                                exchange='binance',
                                symbol=symbol,
                                price=(bucket['bid'] + bucket['ask']) / 2,
                                bid=bucket['bid'],
                                ask=bucket['ask'],
                                bid_size=bucket.get('bid_size'),
                                ask_size=bucket.get('ask_size'),
                                bid_levels=bucket.get('bid_levels'),
                                ask_levels=bucket.get('ask_levels'),
                                ts=bucket.get('ts', 0),
                            )
                        )


class BybitTickerFeed:
    def __init__(self, symbols: list[str], queue: asyncio.Queue):
        self.symbols = symbols
        self.queue = queue

    async def run(self):
        url = 'wss://stream.bybit.com/v5/public/linear'
        topics = [f'tickers.{symbol}' for symbol in self.symbols] + [f'orderbook.50.{symbol}' for symbol in self.symbols]
        state: dict[str, dict] = {}

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url, heartbeat=20) as ws:
                await ws.send_json({'op': 'subscribe', 'args': topics})
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    payload = json.loads(msg.data)
                    topic = payload.get('topic', '')
                    if not topic:
                        continue
                    parts = topic.split('.')
                    symbol = parts[-1]
                    bucket = state.setdefault(symbol, {})

                    if topic.startswith('tickers.'):
                        rows = payload.get('data', {})
                        if isinstance(rows, list):
                            if not rows:
                                continue
                            rows = rows[0]
                        bid = rows.get('bid1Price')
                        ask = rows.get('ask1Price')
                        bucket['bid'] = float(bid) if bid else None
                        bucket['ask'] = float(ask) if ask else None
                        bucket['bid_size'] = float(rows.get('bid1Size') or 0)
                        bucket['ask_size'] = float(rows.get('ask1Size') or 0)
                        bucket['price'] = float(rows.get('markPrice') or rows.get('lastPrice'))
                        bucket['ts'] = payload.get('ts', 0) / 1000
                    elif topic.startswith('orderbook.50.'):
                        data = payload.get('data', {})
                        bucket['bid_levels'] = [(float(price), float(size)) for price, size in data.get('b', [])]
                        bucket['ask_levels'] = [(float(price), float(size)) for price, size in data.get('a', [])]
                        bucket['ts'] = payload.get('ts', 0) / 1000

                    if 'price' in bucket:
                        await self.queue.put(
                            TickerSnapshot(
                                exchange='bybit',
                                symbol=symbol,
                                price=bucket['price'],
                                bid=bucket.get('bid'),
                                ask=bucket.get('ask'),
                                bid_size=bucket.get('bid_size'),
                                ask_size=bucket.get('ask_size'),
                                bid_levels=bucket.get('bid_levels'),
                                ask_levels=bucket.get('ask_levels'),
                                ts=bucket.get('ts', 0),
                            )
                        )
