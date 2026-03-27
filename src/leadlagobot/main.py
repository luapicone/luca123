import asyncio
from collections import defaultdict

from leadlagobot.engine.metrics import PairMetricsTracker
from leadlagobot.config.settings import settings
from leadlagobot.engine.paper_executor import PaperExecutor
from leadlagobot.engine.strategy import (
    calculate_gap_pct,
    estimate_quality_score,
    estimate_signal_age_ms,
    normalized_price,
    should_close_trade,
    should_open_trade,
)
from leadlagobot.exchanges.live_feeds import BinanceTickerFeed, BybitTickerFeed
from leadlagobot.exchanges.mock_feeds import MockExchangeFeed
from leadlagobot.utils.logger import log_trade, print_event
from leadlagobot.utils.status import StatusBoard


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
    status = StatusBoard()
    prices = defaultdict(dict)

    while True:
        tick = await queue.get()
        prices[tick.symbol][tick.exchange] = tick

        if 'binance' not in prices[tick.symbol] or 'bybit' not in prices[tick.symbol]:
            continue

        top_symbols = metrics.get_top_symbols()
        if top_symbols and tick.symbol not in top_symbols and tick.symbol not in executor.open_positions:
            continue

        leader_tick = prices[tick.symbol]['binance']
        follower_tick = prices[tick.symbol]['bybit']
        leader_price = normalized_price(leader_tick.price, leader_tick)
        follower_price = normalized_price(follower_tick.price, follower_tick)
        gap_pct = calculate_gap_pct(leader_price, follower_price)
        signal_age_ms = estimate_signal_age_ms(leader_tick, follower_tick)
        quality_score = estimate_quality_score(gap_pct, signal_age_ms, follower_tick)
        metrics.register_signal(tick.symbol, signal_age_ms, quality_score)

        if tick.symbol not in executor.open_positions:
            if should_open_trade(gap_pct, quality_score, signal_age_ms):
                position = executor.open_position(tick.symbol, leader_tick, follower_tick, gap_pct)
                if position:
                    metrics.register_open(tick.symbol, gap_pct, position.fill_ratio)
                    metrics.flush()
                    follower_bid = follower_tick.bid if follower_tick.bid is not None else follower_tick.price
                    follower_ask = follower_tick.ask if follower_tick.ask is not None else follower_tick.price
                    print_event(
                        f"[green]OPEN[/green] {tick.symbol} gap={gap_pct:.4f}% quality={quality_score:.4f} age={signal_age_ms:.0f}ms fill={position.fill_ratio:.2f} leader={leader_price:.6f} follower_bid={follower_bid:.6f} follower_ask={follower_ask:.6f}"
                    )
                else:
                    fill_ratio = executor.estimate_fill_ratio(
                        settings.notional_usd,
                        follower_tick.ask_size,
                        follower_tick.ask or follower_tick.price,
                        follower_tick.ask_levels,
                    )
                    metrics.register_cancelled(tick.symbol, 'entry', 'insufficient_depth', fill_ratio)
                    metrics.flush()
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
                    f"[cyan]CLOSE[/cyan] {trade.symbol} net={trade.net_pnl:.4f} usd gross={trade.gross_pnl:.4f} fees={trade.fees:.4f} slip={trade.slippage_cost:.4f} fill={trade.fill_ratio:.2f} duration={trade.duration_ms:.0f}ms balance={executor.balance:.2f}"
                )
            else:
                position = executor.open_positions.get(tick.symbol)
                fill_ratio = executor.estimate_fill_ratio(
                    (position.qty * (follower_tick.bid or follower_tick.price)) if position else settings.notional_usd,
                    follower_tick.bid_size,
                    follower_tick.bid or follower_tick.price,
                    follower_tick.bid_levels,
                )
                metrics.register_cancelled(tick.symbol, 'exit', 'insufficient_depth', fill_ratio)
                metrics.flush()

        status.write(
            {
                'balance': executor.balance,
                'open_positions': list(executor.open_positions.keys()),
                'tracked_symbol': tick.symbol,
                'top_symbols': sorted(list(metrics.get_top_symbols())),
                'latest_gap_pct': gap_pct,
                'latest_quality_score': quality_score,
                'latest_signal_age_ms': signal_age_ms,
                'leader_price': leader_price,
                'follower_price': follower_price,
            }
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
