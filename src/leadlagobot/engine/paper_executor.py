from time import time
from leadlagobot.config.settings import settings
from leadlagobot.models.types import ClosedPaperTrade, PaperPosition, TickerSnapshot


class PaperExecutor:
    def __init__(self):
        self.balance = settings.paper_initial_balance
        self.open_positions: dict[str, PaperPosition] = {}
        self.closed_trades: list[ClosedPaperTrade] = []

    def _base_slippage_cost(self, notional: float) -> float:
        return notional * (settings.paper_slippage_bps / 10000)

    def _depth_penalty(self, notional: float, size: float | None, price: float | None) -> float:
        if not size or not price:
            return self._base_slippage_cost(notional)
        visible_depth_usd = size * price * settings.paper_depth_safety_factor
        if visible_depth_usd <= 0:
            return self._base_slippage_cost(notional)
        pressure = min(3.0, notional / visible_depth_usd)
        return self._base_slippage_cost(notional) * pressure

    def open_position(self, symbol: str, leader_tick: TickerSnapshot, follower_tick: TickerSnapshot, gap_pct: float):
        if symbol in self.open_positions:
            return None

        entry_price = follower_tick.ask or follower_tick.price
        qty = settings.notional_usd / entry_price
        self.open_positions[symbol] = PaperPosition(
            symbol=symbol,
            leader_exchange='binance',
            follower_exchange='bybit',
            leader_price=leader_tick.price,
            follower_entry_price=entry_price,
            follower_entry_bid=follower_tick.bid,
            follower_entry_ask=follower_tick.ask,
            qty=qty,
            entry_gap_pct=gap_pct,
        )
        return self.open_positions[symbol]

    def close_position(self, symbol: str, leader_tick: TickerSnapshot, follower_tick: TickerSnapshot, exit_gap_pct: float):
        position = self.open_positions.pop(symbol, None)
        if not position:
            return None

        exit_price = follower_tick.bid or follower_tick.price
        gross_pnl = (leader_tick.price - exit_price) * position.qty
        fees = settings.notional_usd * (settings.binance_fee_rate + settings.bybit_fee_rate)
        open_slippage = self._depth_penalty(settings.notional_usd, follower_tick.ask_size, follower_tick.ask or follower_tick.price)
        close_slippage = self._depth_penalty(settings.notional_usd, follower_tick.bid_size, follower_tick.bid or follower_tick.price)
        slippage_cost = open_slippage + close_slippage
        net_pnl = gross_pnl - fees - slippage_cost
        self.balance += net_pnl

        trade = ClosedPaperTrade(
            symbol=symbol,
            entry_gap_pct=position.entry_gap_pct,
            exit_gap_pct=exit_gap_pct,
            qty=position.qty,
            entry_price=position.follower_entry_price,
            exit_price=exit_price,
            gross_pnl=gross_pnl,
            fees=fees,
            slippage_cost=slippage_cost,
            net_pnl=net_pnl,
            duration_ms=(time() - position.opened_at) * 1000,
        )
        self.closed_trades.append(trade)
        return trade
