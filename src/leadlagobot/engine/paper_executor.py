from time import time
from leadlagobot.config.settings import settings
from leadlagobot.models.types import ClosedPaperTrade, PaperPosition


class PaperExecutor:
    def __init__(self):
        self.balance = settings.paper_initial_balance
        self.open_positions: dict[str, PaperPosition] = {}
        self.closed_trades: list[ClosedPaperTrade] = []

    def _slippage_cost(self, notional: float) -> float:
        return notional * (settings.paper_slippage_bps / 10000)

    def open_position(self, symbol: str, leader_price: float, follower_price: float, gap_pct: float):
        if symbol in self.open_positions:
            return None

        qty = settings.notional_usd / follower_price
        self.open_positions[symbol] = PaperPosition(
            symbol=symbol,
            leader_exchange='binance',
            follower_exchange='bybit',
            leader_price=leader_price,
            follower_entry_price=follower_price,
            qty=qty,
            entry_gap_pct=gap_pct,
        )
        return self.open_positions[symbol]

    def close_position(self, symbol: str, follower_exit_price: float, exit_gap_pct: float):
        position = self.open_positions.pop(symbol, None)
        if not position:
            return None

        gross_pnl = (position.leader_price - follower_exit_price) * position.qty
        fees = settings.notional_usd * (settings.binance_fee_rate + settings.bybit_fee_rate)
        slippage_cost = self._slippage_cost(settings.notional_usd) * 2
        net_pnl = gross_pnl - fees - slippage_cost
        self.balance += net_pnl

        trade = ClosedPaperTrade(
            symbol=symbol,
            entry_gap_pct=position.entry_gap_pct,
            exit_gap_pct=exit_gap_pct,
            qty=position.qty,
            gross_pnl=gross_pnl,
            fees=fees,
            slippage_cost=slippage_cost,
            net_pnl=net_pnl,
            duration_ms=(time() - position.opened_at) * 1000,
        )
        self.closed_trades.append(trade)
        return trade
