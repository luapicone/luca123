# WARNING: This bot uses leverage-style assumptions in paper mode only.
# WARNING: Always test with --dry-run for at least 7 days before live trading.
# WARNING: Past backtest performance does not guarantee live results.
# WARNING: Slippage on market orders during high volatility can exceed SL targets.
# WARNING: You are solely responsible for any financial losses.

SYMBOL = 'ETHUSDT'
LEVERAGE = 45
RISK_PER_TRADE = 0.0030
STOP_PCT = 0.0004
TARGET_PCT = 0.0006
MAX_HOLD_SECONDS = 180
FEE_PCT = 0.0008
SPREAD_MAX_PCT = 0.0003
RSI_PERIOD = 14
RSI_MIN = 35
RSI_MAX = 65
VOLUME_MA_PERIOD = 20
ROUND_NUMBER_BUFFER = 0.001
ORDER_BOOK_LEVELS = 10
DELTA_IMBALANCE_MIN = 1.5
DAILY_LOSS_LIMIT = 0.05
SESSION_DRAWDOWN_LIMIT = 0.03
CONSECUTIVE_LOSS_PAUSE = 5
CONSECUTIVE_LOSS_SIZE_TRIGGER = 3
FUNDING_RATE_MAX = 0.0010
VOLUME_MIN_RATIO = 0.50
WEEKLY_WR_MIN = 0.55
INITIAL_BALANCE = 20.0
EXCHANGE = 'binanceusdm'
SESSIONS = [
    {'name': 'Asia', 'start': '00:00', 'end': '03:00', 'frequency_multiplier': 0.70},
    {'name': 'London', 'start': '07:00', 'end': '10:00', 'frequency_multiplier': 1.00},
    {'name': 'NY', 'start': '13:00', 'end': '16:00', 'frequency_multiplier': 1.00},
]
