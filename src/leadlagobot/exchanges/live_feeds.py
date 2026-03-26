import asyncio
import json
import aiohttp
from leadlagobot.models.types import TickerSnapshot


class BinanceTickerFeed:
    def __init__(self, symbols: list[str], queue: asyncio.Queue):
        self.symbols = [symbol.lower() for symbol in symbols]
        self.queue = queue

    async def run(self):
        stream_names = '/'.join(f'{symbol}@bookTicker' for symbol in self.symbols)
        url = f'wss://fstream.binance.com/stream?streams={stream_names}'

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url, heartbeat=20) as ws:
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    payload = json.loads(msg.data)
                    data = payload.get('data', {})
                    symbol = data.get('s')
                    bid = data.get('b')
                    ask = data.get('a')
                    bid_size = data.get('B')
                    ask_size = data.get('A')
                    event_ts = data.get('E')
                    if not symbol or bid is None or ask is None:
                        continue
                    bid_f = float(bid)
                    ask_f = float(ask)
                    await self.queue.put(
                        TickerSnapshot(
                            exchange='binance',
                            symbol=symbol,
                            price=(bid_f + ask_f) / 2,
                            bid=bid_f,
                            ask=ask_f,
                            bid_size=float(bid_size or 0),
                            ask_size=float(ask_size or 0),
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
                        symbol = payload['topic'].split('.', 1)[1]
                        rows = payload.get('data', {})
                        if isinstance(rows, list):
                            if not rows:
                                continue
                            rows = rows[0]
                        bid = rows.get('bid1Price')
                        ask = rows.get('ask1Price')
                        bid_size = rows.get('bid1Size')
                        ask_size = rows.get('ask1Size')
                        mark = rows.get('markPrice') or rows.get('lastPrice')
                        ts = payload.get('ts', 0) / 1000
                        if not mark:
                            continue
                        bid_f = float(bid) if bid else None
                        ask_f = float(ask) if ask else None
                        await self.queue.put(
                            TickerSnapshot(
                                exchange='bybit',
                                symbol=symbol,
                                price=float(mark),
                                bid=bid_f,
                                ask=ask_f,
                                bid_size=float(bid_size or 0),
                                ask_size=float(ask_size or 0),
                                ts=ts,
                            )
                        )
