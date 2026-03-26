from leadlagobot.config.settings import settings


def calculate_gap_pct(leader_price: float, follower_price: float) -> float:
    return ((leader_price - follower_price) / follower_price) * 100


def should_open_trade(gap_pct: float) -> bool:
    return gap_pct >= settings.entry_threshold_pct


def should_close_trade(gap_pct: float) -> bool:
    return gap_pct <= settings.exit_threshold_pct
