import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class LiveSettings:
    enabled: bool
    api_key: str | None
    api_secret: str | None
    max_live_concurrent_trades: int
    max_live_symbol_notional: float
    require_manual_post_only_review: bool


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def load_live_settings() -> LiveSettings:
    return LiveSettings(
        enabled=_env_bool('LIVE_TRADING', False),
        api_key=os.getenv('BINANCE_API_KEY'),
        api_secret=os.getenv('BINANCE_API_SECRET'),
        max_live_concurrent_trades=int(os.getenv('MAX_LIVE_CONCURRENT_TRADES', '1')),
        max_live_symbol_notional=float(os.getenv('MAX_LIVE_SYMBOL_NOTIONAL', '10')),
        require_manual_post_only_review=_env_bool('REQUIRE_MANUAL_POST_ONLY_REVIEW', True),
    )


def validate_live_settings(settings: LiveSettings):
    if not settings.enabled:
        return True, 'live_trading_disabled'
    if not settings.api_key or not settings.api_secret:
        return False, 'missing_binance_api_credentials'
    if settings.max_live_concurrent_trades > 1:
        return False, 'live_concurrent_trade_limit_must_stay_at_1_for_initial_rollout'
    if settings.max_live_symbol_notional > 10:
        return False, 'live_symbol_notional_limit_must_stay_at_or_below_10_for_initial_rollout'
    return True, None
