import asyncio
from collections import defaultdict

from leadlagobot.engine.metrics import PairMetricsTracker
from leadlagobot.config.settings import settings
from leadlagobot.engine.paper_executor import PaperExecutor
from leadlagobot.engine.strategy import (
    calculate_gap_pct,
    estimate_quality_score,
    estimate_signal_age_ms,
    should_close_trade,
    should_open_trade,
)
from leadlagobot.exchanges.live_feeds import BinanceTickerFeed, BybitTickerFeed
from leadlagobot.exchanges.mock_feeds import MockExchangeFeed
from leadlagobot.utils.logger import log_trade, print_event


def rejection_reason(gap_pct: float, quality_score: float, signal_age_ms: float) -> str:
    reasons = []
    if gap_pct < settings.entry_threshold_pct:
        reasons.append('gap_below_threshold')
    if quality_score < settings.min_quality_score:
        reasons.append('quality_below_threshold')
    if signal_age_ms > settings.max_signal_age_ms:
        reasons.append('signal_too_old')
    return ','.join(reasons) if reasons else 'unknown'


async def engine_loop(queue: asyncio.Queue):
    executor = PaperExecutor()
    metrics = PairMetricsTracker()
    prices = defaultdict(dict)

    while True:
        tick = await queue.get()
        prices[tick.symbol][tick.exchange] = tick

        if 'binance' not in prices[tick.symbol] or 'bybit' not in prices[tick.symbol]:
            continue

        leader_tick = prices[tick.symbol]['binance']
        follower_tick = prices[tick.symbol]['bybit']
        gap_pct = calculate_gap_pct(leader_tick.price, follower_tick.price)
        signal_age_ms = estimate_signal_age_ms(leader_tick, follower_tick)
        quality_score = estimate_quality_score(gap_pct, signal_age_ms, follower_tick)
        metrics.register_signal(tick.symbol, signal_age_ms, quality_score)

        if tick.symbol not in executor.open_positions:
            if should_open_trade(gap_pct, quality_score, signal_age_ms):
                position = executor.open_position(tick.symbol, leader_tick, follower_tick, gap_pct)
                if position:
                    metrics.register_open(tick.symbol, gap_pct)
                    metrics.flush()
                    follower_bid = follower_tick.bid if follower_tick.bid is not None else follower_tick.price
                    follower_ask = follower_tick.ask if follower_tick.ask is not None else follower_tick.price
                    print_event(
                        f"[green]OPEN[/green] {tick.symbol} gap={gap_pct:.4f}% quality={quality_score:.4f} age={signal_age_ms:.0f}ms leader={leader_tick.price:.6f} follower_bid={follower_bid:.6f} follower_ask={follower_ask:.6f}"
                    )
            else:
                metrics.register_rejected(
                    tick.symbol,
                    gap_pct,
                    quality_score,
                    signal_age_ms,
                    rejection_reason(gap_pct, quality_score, signal_age_ms),
                )
                metrics.flush()

        elif should_close_trade(gap_pct):
            trade = executor.close_position(tick.symbol, leader_tick, follower_tick, gap_pct)
            if trade:
                metrics.register_close(trade)
                metrics.flush()
                log_trade(trade)
                print_event(
                    f"[cyan]CLOSE[/cyan] {trade.symbol} net={trade.net_pnl:.4f} usd gross={trade.gross_pnl:.4f} fees={trade.fees:.4f} slip={trade.slippage_cost:.4f} duration={trade.duration_ms:.0f}ms balance={executor.balance:.2f}"
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
