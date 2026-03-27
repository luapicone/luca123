from dataclasses import dataclass, field
from time import time


@dataclass
class TickerSnapshot:
    exchange: str
    symbol: str
    price: float
    bid: float | None = None
    ask: float | None = None
    bid_size: float | None = None
    ask_size: float | None = None
    bid_levels: list[tuple[float, float]] | None = None
    ask_levels: list[tuple[float, float]] | None = None
    ts: float = field(default_factory=time)


@dataclass
class PaperPosition:
    symbol: str
    leader_exchange: str
    follower_exchange: str
    leader_price: float
    follower_entry_price: float
    follower_entry_bid: float | None
    follower_entry_ask: float | None
    qty: float
    requested_qty: float
    fill_ratio: float
    entry_gap_pct: float
    expected_net_edge_pct: float = 0.0
    peak_gap_pct: float = 0.0
    opened_at: float = field(default_factory=time)


@dataclass
class ClosedPaperTrade:
    symbol: str
    entry_gap_pct: float
    exit_gap_pct: float
    qty: float
    requested_qty: float
    fill_ratio: float
    entry_price: float
    exit_price: float
    gross_pnl: float
    fees: float
    slippage_cost: float
    net_pnl: float
    expected_net_edge_pct: float
    realized_fee_pct: float
    realized_slippage_pct: float
    realized_net_edge_pct: float
    duration_ms: float
