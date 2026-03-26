import asyncio
import json
import aiohttp
from leadlagobot.models.types import TickerSnapshot


class BinanceTickerFeed:
    def __init__(self, symbols: list[str], queue: asyncio.Queue):
        self.symbols = [symbol.lower() for symbol in symbols]
        self.queue = queue

    async def run(self):
        stream_names = '/'.join(f'{symbol}@markPrice' for symbol in self.symbols)
        url = f'wss://fstream.binance.com/stream?streams={stream_names}'

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url, heartbeat=20) as ws:
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    payload = json.loads(msg.data)
                    data = payload.get('data', {})
                    symbol = data.get('s')
                    price = data.get('p')
                    event_ts = data.get('E')
                    if not symbol or price is None:
                        continue
                    await self.queue.put(
                        TickerSnapshot(
                            exchange='binance',
                            symbol=symbol,
                            price=float(price),
                            ts=(event_ts or 0) / 1000,
                        )
                    )


class BybitTickerFeed:
    def __init__(self, symbols: list[str], queue: asyncio.Queue):
        self.symbols = symbols
        self.queue = queue

    async def run(self):
        url = 'wss://stream.bybit.com/v5/public/linear'
        topics = [f'tickers.{symbol}' for symbol in self.symbols]

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url, heartbeat=20) as ws:
                await ws.send_json({'op': 'subscribe', 'args': topics})
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    payload = json.loads(msg.data)
                    if payload.get('topic', '').startswith('tickers.'):
                        topic = payload['topic']
                        symbol = topic.split('.', 1)[1]
                        rows = payload.get('data', {})
                        if isinstance(rows, list):
                            if not rows:
                                continue
                            rows = rows[0]
                        price = rows.get('markPrice') or rows.get('lastPrice')
                        ts = payload.get('ts', 0) / 1000
                        if not price:
                            continue
                        await self.queue.put(
                            TickerSnapshot(
                                exchange='bybit',
                                symbol=symbol,
                                price=float(price),
                                ts=ts,
                            )
                        )
