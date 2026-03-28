# WARNING: This bot uses leverage-style assumptions in paper mode only.
# WARNING: Always test with --dry-run for at least 7 days before live trading.
# WARNING: Past backtest performance does not guarantee live results.
# WARNING: Slippage on market orders during high volatility can exceed SL targets.
# WARNING: You are solely responsible for any financial losses.

SYMBOL = 'ETH/USDT:USDT'
LEVERAGE = 45
RISK_PER_TRADE = 0.0020
STOP_PCT = 0.0010
TARGET_PCT = 0.0025
MAX_HOLD_SECONDS = 150
FEE_PCT = 0.0004
SPREAD_MAX_PCT = 0.0006
RSI_PERIOD = 14
RSI_MIN = 42
RSI_MAX = 58
VOLUME_MA_PERIOD = 20
ROUND_NUMBER_BUFFER = 0.0008
ORDER_BOOK_LEVELS = 10
DELTA_IMBALANCE_MIN = 1.35
DAILY_LOSS_LIMIT = 0.08
SESSION_DRAWDOWN_LIMIT = 0.06
CONSECUTIVE_LOSS_PAUSE = 4
CONSECUTIVE_LOSS_SIZE_TRIGGER = 2
FUNDING_RATE_MAX = 0.0010
VOLUME_MIN_RATIO = 0.45
WEEKLY_WR_MIN = 0.52
INITIAL_BALANCE = 20.0
EXCHANGE = 'binanceusdm'
IGNORE_SESSIONS = True
PRICE_WINDOW = 8
MICRO_PULLBACK_BARS = 3
MOMENTUM_MIN_PCT = 0.00045
RECLAIM_THRESHOLD_PCT = 0.00015
BREAKEVEN_TRIGGER_PCT = 0.0009
TRAILING_TRIGGER_PCT = 0.0012
TRAILING_GIVEBACK_PCT = 0.00045
EARLY_FAIL_BARS = 5
SESSIONS = [
    {'name': 'Asia', 'start': '00:00', 'end': '03:00', 'frequency_multiplier': 0.70},
    {'name': 'London', 'start': '07:00', 'end': '10:00', 'frequency_multiplier': 1.00},
    {'name': 'NY', 'start': '13:00', 'end': '16:00', 'frequency_multiplier': 1.00},
]
