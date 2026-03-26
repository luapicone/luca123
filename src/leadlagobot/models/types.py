from dataclasses import dataclass, field
from time import time


@dataclass
class TickerSnapshot:
    exchange: str
    symbol: str
    price: float
    ts: float = field(default_factory=time)


@dataclass
class PaperPosition:
    symbol: str
    leader_exchange: str
    follower_exchange: str
    leader_price: float
    follower_entry_price: float
    qty: float
    entry_gap_pct: float
    opened_at: float = field(default_factory=time)


@dataclass
class ClosedPaperTrade:
    symbol: str
    entry_gap_pct: float
    exit_gap_pct: float
    qty: float
    gross_pnl: float
    fees: float
    slippage_cost: float
    net_pnl: float
    duration_ms: float
