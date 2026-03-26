import asyncio
from collections import defaultdict

from leadlagobot.config.settings import settings
from leadlagobot.engine.paper_executor import PaperExecutor
from leadlagobot.engine.strategy import calculate_gap_pct, should_close_trade, should_open_trade
from leadlagobot.exchanges.live_feeds import BinanceTickerFeed, BybitTickerFeed
from leadlagobot.exchanges.mock_feeds import MockExchangeFeed
from leadlagobot.utils.logger import log_trade, print_event


async def engine_loop(queue: asyncio.Queue):
    executor = PaperExecutor()
    prices = defaultdict(dict)

    while True:
        tick = await queue.get()
        prices[tick.symbol][tick.exchange] = tick.price

        if 'binance' not in prices[tick.symbol] or 'bybit' not in prices[tick.symbol]:
            continue

        leader_price = prices[tick.symbol]['binance']
        follower_price = prices[tick.symbol]['bybit']
        gap_pct = calculate_gap_pct(leader_price, follower_price)

        if tick.symbol not in executor.open_positions and should_open_trade(gap_pct):
            position = executor.open_position(tick.symbol, leader_price, follower_price, gap_pct)
            if position:
                print_event(
                    f"[green]OPEN[/green] {tick.symbol} gap={gap_pct:.4f}% leader={leader_price:.6f} follower={follower_price:.6f}"
                )

        elif tick.symbol in executor.open_positions and should_close_trade(gap_pct):
            trade = executor.close_position(tick.symbol, follower_price, gap_pct)
            if trade:
                log_trade(trade)
                print_event(
                    f"[cyan]CLOSE[/cyan] {trade.symbol} net={trade.net_pnl:.4f} usd duration={trade.duration_ms:.0f}ms balance={executor.balance:.2f}"
                )


async def main():
    queue = asyncio.Queue()

    if settings.feed_mode == 'mock':
        tasks = [
            asyncio.create_task(MockExchangeFeed('binance', settings.symbols, queue, leader_bias=True).run()),
            asyncio.create_task(MockExchangeFeed('bybit', settings.symbols, queue, leader_bias=False).run()),
            asyncio.create_task(engine_loop(queue)),
        ]
    else:
        tasks = [
            asyncio.create_task(BinanceTickerFeed(settings.symbols, queue).run()),
            asyncio.create_task(BybitTickerFeed(settings.symbols, queue).run()),
            asyncio.create_task(engine_loop(queue)),
        ]

    await asyncio.gather(*tasks)


if __name__ == '__main__':
    asyncio.run(main())
