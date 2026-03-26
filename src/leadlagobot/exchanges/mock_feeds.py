import asyncio
import random
from time import time
from leadlagobot.models.types import TickerSnapshot


class MockExchangeFeed:
    def __init__(self, exchange: str, symbols: list[str], queue: asyncio.Queue, leader_bias: bool = False):
        self.exchange = exchange
        self.symbols = symbols
        self.queue = queue
        self.leader_bias = leader_bias
        self.base_prices = {symbol: random.uniform(0.5, 500) for symbol in symbols}

    async def run(self):
        while True:
            for symbol in self.symbols:
                move = random.uniform(-0.002, 0.002)
                lag_bonus = random.uniform(0.0004, 0.0025) if self.leader_bias else 0
                self.base_prices[symbol] *= 1 + move + lag_bonus
                mid = round(self.base_prices[symbol], 6)
                spread = max(mid * random.uniform(0.0001, 0.0006), 0.000001)
                bid = mid - spread / 2
                ask = mid + spread / 2
                bid_size = random.uniform(50, 5000)
                ask_size = random.uniform(50, 5000)

                await self.queue.put(
                    TickerSnapshot(
                        exchange=self.exchange,
                        symbol=symbol,
                        price=mid,
                        bid=bid,
                        ask=ask,
                        bid_size=bid_size,
                        ask_size=ask_size,
                        ts=time(),
                    )
                )
            await asyncio.sleep(0.15 if self.leader_bias else 0.22)
