from collections import deque, defaultdict
from statistics import mean, pstdev
from time import time

from leadlagobot.config.settings import settings
from leadlagobot.models.types import ClosedPaperTrade, TickerSnapshot


class MeanReversionPaperTrader:
    def __init__(self):
        self.balance = settings.paper_initial_balance
        self.history = defaultdict(lambda: deque(maxlen=settings.mr_lookback))
        self.positions = {}
        self.closed_trades: list[ClosedPaperTrade] = []

    def update_price(self, tick: TickerSnapshot):
        self.history[tick.symbol].append({'price': tick.price, 'ts': tick.ts})

    def signal_features(self, symbol: str):
        rows = self.history[symbol]
        if len(rows) < max(10, settings.mr_lookback // 2):
            return None
        prices = [row['price'] for row in rows]
        avg = mean(prices)
        std = pstdev(prices) or 1e-9
        current = prices[-1]
        zscore = (current - avg) / std
        return {
            'price': current,
            'mean_price': avg,
            'std_price': std,
            'zscore': zscore,
            'distance_pct': ((current - avg) / avg) * 100 if avg else 0.0,
        }

    def should_open_long(self, features: dict):
        return features['zscore'] <= -settings.mr_entry_zscore

    def should_close_long(self, features: dict, opened_at: float):
        held_ms = (time() - opened_at) * 1000
        if held_ms < settings.mr_min_hold_ms:
            return False
        if features['zscore'] >= -settings.mr_exit_zscore:
            return True
        if held_ms >= settings.mr_max_hold_ms:
            return True
        return False

    def open_long(self, symbol: str, tick: TickerSnapshot, features: dict):
        if symbol in self.positions:
            return None
        qty = settings.notional_usd / max(tick.price, 1e-9)
        self.positions[symbol] = {
            'entry_price': tick.price,
            'qty': qty,
            'opened_at': time(),
            'entry_zscore': features['zscore'],
            'entry_distance_pct': features['distance_pct'],
        }
        return self.positions[symbol]

    def close_long(self, symbol: str, tick: TickerSnapshot, features: dict):
        position = self.positions.pop(symbol, None)
        if not position:
            return None
        entry_notional = position['qty'] * position['entry_price']
        exit_notional = position['qty'] * tick.price
        gross_pnl = (tick.price - position['entry_price']) * position['qty']
        fees = (entry_notional + exit_notional) * (settings.binance_fee_rate * 0.5)
        slippage_cost = (entry_notional + exit_notional) * ((settings.paper_slippage_bps / 10000) * 0.5)
        net_pnl = gross_pnl - fees - slippage_cost
        self.balance += net_pnl
        trade = ClosedPaperTrade(
            symbol=symbol,
            entry_gap_pct=position['entry_distance_pct'],
            exit_gap_pct=features['distance_pct'],
            qty=position['qty'],
            requested_qty=position['qty'],
            fill_ratio=1.0,
            entry_price=position['entry_price'],
            exit_price=tick.price,
            gross_pnl=gross_pnl,
            fees=fees,
            slippage_cost=slippage_cost,
            net_pnl=net_pnl,
            expected_net_edge_pct=abs(position['entry_zscore']),
            realized_fee_pct=(fees / max(entry_notional, 1e-9)) * 100,
            realized_slippage_pct=(slippage_cost / max(entry_notional, 1e-9)) * 100,
            realized_net_edge_pct=(net_pnl / max(entry_notional, 1e-9)) * 100,
            duration_ms=(time() - position['opened_at']) * 1000,
        )
        self.closed_trades.append(trade)
        return trade
