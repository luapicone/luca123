import asyncio
from collections import defaultdict

from leadlagobot.account_sync import fetch_account_snapshot
from leadlagobot.contracts import validate_symbol_rules, update_rules
from leadlagobot.engine.metrics import PairMetricsTracker
from leadlagobot.config.settings import settings
from leadlagobot.engine.paper_executor import PaperExecutor
from leadlagobot.engine.strategy import (
    calculate_gap_pct,
    estimate_expected_cost_pct,
    estimate_quality_score,
    estimate_signal_age_ms,
    normalized_price,
    should_close_trade,
    should_open_trade,
)
from leadlagobot.exchange_metadata import fetch_binance_metadata, fetch_bybit_metadata
from leadlagobot.exchanges.live_feeds import BinanceTickerFeed, BybitTickerFeed
from leadlagobot.exchanges.mock_feeds import MockExchangeFeed
from leadlagobot.execution import ExecutionIntent, RealExecutionAdapter
from leadlagobot.margin import MarginValidator
from leadlagobot.reconciliation import ReconciliationStore
from leadlagobot.risk import RiskEngine
from leadlagobot.utils.logger import log_trade, print_event
from leadlagobot.utils.status import StatusBoard


def rejection_reason(gap_pct: float, quality_score: float, signal_age_ms: float, expected_net_edge_pct: float) -> str:
    reasons = []
    if gap_pct < settings.entry_threshold_pct:
        reasons.append('gap_below_threshold')
    if quality_score < settings.min_quality_score:
        reasons.append('quality_below_threshold')
    if signal_age_ms > settings.max_signal_age_ms:
        reasons.append('signal_too_old')
    if expected_net_edge_pct <= 0:
        reasons.append('edge_below_cost')
    return ','.join(reasons) if reasons else 'unknown'


async def bootstrap_metadata():
    try:
        binance = await fetch_binance_metadata(settings.symbols)
        bybit = await fetch_bybit_metadata(settings.symbols)
        update_rules({**binance, **bybit})
    except Exception:
        pass


async def engine_loop(queue: asyncio.Queue):
    executor = PaperExecutor()
    execution_adapter = RealExecutionAdapter()
    metrics = PairMetricsTracker()
    margin = MarginValidator()
    risk = RiskEngine()
    risk.load()
    reconciliation = ReconciliationStore()
    status = StatusBoard()
    prices = defaultdict(dict)
    execution_snapshot = {}

    while True:
        tick = await queue.get()
        prices[tick.symbol][tick.exchange] = tick
        risk.register_signal()

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

        preview_fill_ratio = executor.estimate_fill_ratio(
            settings.notional_usd,
            follower_tick.ask_size,
            follower_tick.ask or follower_tick.price,
            follower_tick.ask_levels,
        )
        expected_cost_pct = estimate_expected_cost_pct(follower_tick, preview_fill_ratio)
        expected_net_edge_pct = gap_pct - expected_cost_pct

        current_exposure = len(executor.open_positions) * settings.notional_usd
        expected_worst_loss = settings.notional_usd * max(gap_pct / 100, 0.01)
        risk_ok, risk_reason = risk.validate_entry(
            open_positions=len(executor.open_positions),
            current_exposure_usd=current_exposure,
            expected_worst_loss_usd=expected_worst_loss,
        )
        margin_ok, margin_reason = margin.validate(executor.balance, current_exposure, settings.notional_usd)
        qty_preview = settings.notional_usd / max(follower_price, 1e-9)
        rules_ok, rules_reason, rules = validate_symbol_rules(tick.symbol, follower_price, qty_preview)

        if tick.symbol not in executor.open_positions:
            if risk_ok and margin_ok and rules_ok and should_open_trade(gap_pct, quality_score, signal_age_ms, expected_net_edge_pct):
                dry_intent = ExecutionIntent(
                    symbol=tick.symbol,
                    side='buy',
                    qty=qty_preview,
                    reference_price=follower_price,
                    exchange='bybit',
                    order_type='market',
                )
                execution_snapshot[tick.symbol] = {'entry_preview': execution_adapter.place_entry(dry_intent, follower_tick)}

                position = executor.open_position(tick.symbol, leader_tick, follower_tick, gap_pct, expected_net_edge_pct)
                if position:
                    metrics.register_open(tick.symbol, gap_pct, position.fill_ratio)
                    metrics.flush()
                    risk.flush()
                    follower_bid = follower_tick.bid if follower_tick.bid is not None else follower_tick.price
                    follower_ask = follower_tick.ask if follower_tick.ask is not None else follower_tick.price
                    print_event(
                        f"[green]OPEN[/green] {tick.symbol} gap={gap_pct:.4f}% edge={expected_net_edge_pct:.4f}% quality={quality_score:.4f} age={signal_age_ms:.0f}ms fill={position.fill_ratio:.2f} leader={leader_price:.6f} follower_bid={follower_bid:.6f} follower_ask={follower_ask:.6f}"
                    )
                else:
                    fill_ratio = executor.estimate_fill_ratio(
                        settings.notional_usd,
                        follower_tick.ask_size,
                        follower_tick.ask or follower_tick.price,
                        follower_tick.ask_levels,
                    )
                    metrics.register_cancelled(tick.symbol, 'entry', 'insufficient_depth', fill_ratio)
                    risk.register_cancel()
                    metrics.flush()
                    risk.flush()
            else:
                fail_reason = (
                    risk_reason if not risk_ok else
                    margin_reason if not margin_ok else
                    rules_reason if not rules_ok else
                    rejection_reason(gap_pct, quality_score, signal_age_ms, expected_net_edge_pct)
                )
                metrics.register_rejected(
                    tick.symbol,
                    gap_pct,
                    quality_score,
                    signal_age_ms,
                    fail_reason,
                )
                metrics.flush()
                risk.flush()

        else:
            position = executor.open_positions.get(tick.symbol)
            if position and should_close_trade(gap_pct, position.entry_gap_pct):
                dry_intent = ExecutionIntent(
                    symbol=tick.symbol,
                    side='sell',
                    qty=position.qty,
                    reference_price=follower_price,
                    exchange='bybit',
                    order_type='market',
                )
                execution_snapshot[tick.symbol] = {'exit_preview': execution_adapter.place_exit(dry_intent, follower_tick)}

                trade = executor.close_position(tick.symbol, leader_tick, follower_tick, gap_pct)
                if trade:
                    risk.register_trade(trade.net_pnl)
                    metrics.register_close(trade)
                    metrics.flush()
                    risk.flush()
                    log_trade(trade)
                    print_event(
                        f"[cyan]CLOSE[/cyan] {trade.symbol} net={trade.net_pnl:.4f} usd gross={trade.gross_pnl:.4f} fees={trade.fees:.4f} slip={trade.slippage_cost:.4f} fill={trade.fill_ratio:.2f} duration={trade.duration_ms:.0f}ms balance={executor.balance:.2f}"
                    )
                else:
                    fill_ratio = executor.estimate_fill_ratio(
                        (position.qty * (follower_tick.bid or follower_tick.price)) if position else settings.notional_usd,
                        follower_tick.bid_size,
                        follower_tick.bid or follower_tick.price,
                        follower_tick.bid_levels,
                    )
                    metrics.register_cancelled(tick.symbol, 'exit', 'insufficient_depth', fill_ratio)
                    risk.register_cancel()
                    metrics.flush()
                    risk.flush()

        account_snapshot = await fetch_account_snapshot()
        reconciliation.write_snapshot(
            executor.open_positions,
            prices,
            account_snapshot=account_snapshot,
            execution_snapshot=execution_snapshot,
        )
        status.write(
            {
                'balance': executor.balance,
                'open_positions': list(executor.open_positions.keys()),
                'tracked_symbol': tick.symbol,
                'top_symbols': sorted(list(metrics.get_top_symbols())),
                'latest_gap_pct': gap_pct,
                'latest_quality_score': quality_score,
                'latest_signal_age_ms': signal_age_ms,
                'expected_cost_pct': expected_cost_pct,
                'expected_net_edge_pct': expected_net_edge_pct,
                'leader_price': leader_price,
                'follower_price': follower_price,
                'risk_ok': risk_ok,
                'risk_reason': risk_reason,
                'margin_ok': margin_ok,
                'margin_reason': margin_reason,
                'rules_ok': rules_ok,
                'rules_reason': rules_reason,
                'daily_realized_pnl': risk.daily_realized_pnl,
                'cancel_rate': risk.cancel_rate(),
                'tick_size': rules.tick_size if rules else None,
                'qty_step': rules.qty_step if rules else None,
                'min_qty': rules.min_qty if rules else None,
                'min_notional': rules.min_notional if rules else None,
                'account_snapshot': account_snapshot,
                'execution_snapshot': execution_snapshot.get(tick.symbol, {}),
            }
        )


async def main():
    await bootstrap_metadata()
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
