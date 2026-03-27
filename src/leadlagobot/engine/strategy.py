from leadlagobot.config.settings import settings
from leadlagobot.models.types import TickerSnapshot


def normalized_price(price: float, tick: TickerSnapshot) -> float:
    if tick.bid and tick.ask:
        return (tick.bid + tick.ask) / 2
    return price


def calculate_gap_pct(leader_price: float, follower_price: float) -> float:
    return ((leader_price - follower_price) / follower_price) * 100


def estimate_signal_age_ms(leader_tick: TickerSnapshot, follower_tick: TickerSnapshot) -> float:
    return abs(leader_tick.ts - follower_tick.ts) * 1000


def estimate_quality_score(gap_pct: float, signal_age_ms: float, follower_tick: TickerSnapshot) -> float:
    spread_penalty = 0.0
    if follower_tick.bid and follower_tick.ask and follower_tick.price > 0:
        spread_penalty = ((follower_tick.ask - follower_tick.bid) / follower_tick.price) * 100

    age_penalty = min(signal_age_ms / max(settings.max_signal_age_ms, 1), 3.0)
    depth_bonus = 0.0
    if follower_tick.bid_size and follower_tick.ask_size:
        depth_bonus = min((follower_tick.bid_size + follower_tick.ask_size) / 10000, 0.25)

    raw = gap_pct - spread_penalty - age_penalty + depth_bonus
    return raw


def estimate_expected_cost_pct(follower_tick: TickerSnapshot, fill_ratio: float) -> float:
    if not follower_tick.price:
        return 999.0

    spread_pct = 0.0
    if follower_tick.bid and follower_tick.ask:
        spread_pct = ((follower_tick.ask - follower_tick.bid) / follower_tick.price) * 100

    fee_pct = (settings.binance_fee_rate + settings.bybit_fee_rate) * 100 * 0.5
    slippage_pct = (settings.paper_slippage_bps / 10000) * 100 * 0.65
    fill_penalty_pct = max(0.0, (1.0 - fill_ratio)) * 0.08
    return fee_pct + spread_pct + slippage_pct + fill_penalty_pct + settings.expected_net_edge_margin_pct


def should_open_trade(gap_pct: float, quality_score: float, signal_age_ms: float, expected_net_edge_pct: float = 0.0) -> bool:
    return (
        gap_pct >= settings.entry_threshold_pct
        and quality_score >= settings.min_quality_score
        and signal_age_ms <= settings.max_signal_age_ms
        and expected_net_edge_pct >= settings.min_expected_net_edge_pct
    )


def should_close_trade(gap_pct: float, entry_gap_pct: float | None = None) -> bool:
    if entry_gap_pct is None:
        return gap_pct <= settings.exit_threshold_pct

    target_gap = min(settings.exit_threshold_pct, entry_gap_pct * settings.min_exit_capture_ratio)
    return gap_pct <= target_gap
