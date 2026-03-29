from datetime import datetime, timedelta, timezone
from reversion_scalp_v1.config import CONSECUTIVE_LOSS_PAUSE, DAILY_LOSS_LIMIT, MAX_TRADES_PER_DAY, PAUSE_MINUTES, SESSION_DRAWDOWN_LIMIT


def risk_checks(state):
    if state.daily_start_balance and (state.daily_start_balance - state.balance) / state.daily_start_balance >= DAILY_LOSS_LIMIT:
        return False, 'daily_loss_limit'
    if state.session_peak_balance and (state.session_peak_balance - state.balance) / state.session_peak_balance >= SESSION_DRAWDOWN_LIMIT:
        return False, 'session_drawdown_limit'
    if state.trades_today >= MAX_TRADES_PER_DAY:
        return False, 'max_trades_per_day'
    if state.pause_until and datetime.now(timezone.utc).timestamp() < state.pause_until:
        return False, 'cooldown_pause'
    if state.consecutive_losses >= CONSECUTIVE_LOSS_PAUSE:
        state.pause_until = (datetime.now(timezone.utc) + timedelta(minutes=PAUSE_MINUTES)).timestamp()
        state.consecutive_losses = 0
        return False, 'consecutive_loss_pause'
    return True, None
