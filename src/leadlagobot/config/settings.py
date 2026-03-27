from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseModel):
    binance_fee_rate: float = float(os.getenv('BINANCE_FEE_RATE', '0.00055'))
    bybit_fee_rate: float = float(os.getenv('BYBIT_FEE_RATE', '0.00055'))
    paper_initial_balance: float = float(os.getenv('PAPER_INITIAL_BALANCE', '10000'))
    paper_slippage_bps: float = float(os.getenv('PAPER_SLIPPAGE_BPS', '4'))
    paper_depth_safety_factor: float = float(os.getenv('PAPER_DEPTH_SAFETY_FACTOR', '0.35'))
    depth_levels_assumed: int = int(os.getenv('DEPTH_LEVELS_ASSUMED', '5'))
    real_execution_enabled: bool = os.getenv('REAL_EXECUTION_ENABLED', 'false').strip().lower() == 'true'
    min_fill_ratio: float = float(os.getenv('MIN_FILL_RATIO', '0.35'))
    entry_threshold_pct: float = float(os.getenv('ENTRY_THRESHOLD_PCT', '0.13'))
    exit_threshold_pct: float = float(os.getenv('EXIT_THRESHOLD_PCT', '0.03'))
    min_quality_score: float = float(os.getenv('MIN_QUALITY_SCORE', '0.15'))
    max_signal_age_ms: float = float(os.getenv('MAX_SIGNAL_AGE_MS', '2500'))
    top_pairs_limit: int = int(os.getenv('TOP_PAIRS_LIMIT', '8'))
    ranking_min_signals: int = int(os.getenv('RANKING_MIN_SIGNALS', '20'))
    notional_usd: float = float(os.getenv('NOTIONAL_USD', '750'))
    feed_mode: str = os.getenv('FEED_MODE', 'live').strip().lower()
    symbols: list[str] = [item.strip().upper() for item in os.getenv('SYMBOLS', 'BRUSDT,LYNUSDT,JCTUSDT').split(',') if item.strip()]


settings = Settings()
