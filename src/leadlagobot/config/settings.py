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
    dry_run_enabled: bool = os.getenv('DRY_RUN_ENABLED', 'true').strip().lower() == 'true'
    real_confirm_token: str = os.getenv('REAL_CONFIRM_TOKEN', '')
    binance_api_key: str = os.getenv('BINANCE_API_KEY', '')
    binance_api_secret: str = os.getenv('BINANCE_API_SECRET', '')
    bybit_api_key: str = os.getenv('BYBIT_API_KEY', '')
    bybit_api_secret: str = os.getenv('BYBIT_API_SECRET', '')
    risk_enabled: bool = os.getenv('RISK_ENABLED', 'true').strip().lower() == 'true'
    kill_switch_file: str = os.getenv('KILL_SWITCH_FILE', 'data/KILL_SWITCH')
    min_fill_ratio: float = float(os.getenv('MIN_FILL_RATIO', '0.45'))
    entry_threshold_pct: float = float(os.getenv('ENTRY_THRESHOLD_PCT', '0.24'))
    exit_threshold_pct: float = float(os.getenv('EXIT_THRESHOLD_PCT', '0.08'))
    min_quality_score: float = float(os.getenv('MIN_QUALITY_SCORE', '0.02'))
    max_signal_age_ms: float = float(os.getenv('MAX_SIGNAL_AGE_MS', '5000'))
    max_daily_loss_usd: float = float(os.getenv('MAX_DAILY_LOSS_USD', '250'))
    max_loss_per_trade_usd: float = float(os.getenv('MAX_LOSS_PER_TRADE_USD', '40'))
    max_open_positions: int = int(os.getenv('MAX_OPEN_POSITIONS', '3'))
    max_exposure_usd: float = float(os.getenv('MAX_EXPOSURE_USD', '2250'))
    max_cancel_rate: float = float(os.getenv('MAX_CANCEL_RATE', '0.95'))
    top_pairs_limit: int = int(os.getenv('TOP_PAIRS_LIMIT', '10'))
    ranking_min_signals: int = int(os.getenv('RANKING_MIN_SIGNALS', '40'))
    ranking_weight_net_pnl: float = float(os.getenv('RANKING_WEIGHT_NET_PNL', '1.0'))
    ranking_weight_quality: float = float(os.getenv('RANKING_WEIGHT_QUALITY', '100.0'))
    ranking_weight_fill: float = float(os.getenv('RANKING_WEIGHT_FILL', '40.0'))
    ranking_weight_win_rate: float = float(os.getenv('RANKING_WEIGHT_WIN_RATE', '25.0'))
    expected_net_edge_margin_pct: float = float(os.getenv('EXPECTED_NET_EDGE_MARGIN_PCT', '0.03'))
    min_expected_net_edge_pct: float = float(os.getenv('MIN_EXPECTED_NET_EDGE_PCT', '-0.02'))
    entry_confirmation_drop_pct: float = float(os.getenv('ENTRY_CONFIRMATION_DROP_PCT', '0.03'))
    min_hold_ms: float = float(os.getenv('MIN_HOLD_MS', '1500'))
    max_hold_ms: float = float(os.getenv('MAX_HOLD_MS', '45000'))
    stop_loss_gap_multiplier: float = float(os.getenv('STOP_LOSS_GAP_MULTIPLIER', '1.15'))
    min_exit_capture_ratio: float = float(os.getenv('MIN_EXIT_CAPTURE_RATIO', '0.35'))
    max_cross_exchange_tick_age_ms: float = float(os.getenv('MAX_CROSS_EXCHANGE_TICK_AGE_MS', '3000'))
    ranking_signal_saturation: float = float(os.getenv('RANKING_SIGNAL_SATURATION', '250.0'))
    ranking_rejection_penalty_cap: float = float(os.getenv('RANKING_REJECTION_PENALTY_CAP', '0.75'))
    ranking_cancel_penalty_cap: float = float(os.getenv('RANKING_CANCEL_PENALTY_CAP', '0.75'))
    notional_usd: float = float(os.getenv('NOTIONAL_USD', '750'))
    feed_mode: str = os.getenv('FEED_MODE', 'live').strip().lower()
    symbols: list[str] = [item.strip().upper() for item in os.getenv('SYMBOLS', 'BRUSDT,LYNUSDT,JCTUSDT').split(',') if item.strip()]


settings = Settings()
