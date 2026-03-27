from datetime import datetime, timedelta, timezone
from tick_vampire_v3.config import DAILY_LOSS_LIMIT, SESSION_DRAWDOWN_LIMIT, CONSECUTIVE_LOSS_PAUSE, WEEKLY_WR_MIN, VOLUME_MIN_RATIO

def risk_checks(state):
    if state.is_halted:
        return False, state.halt_reason or 'halted'
    if state.session_open_balance and (state.session_open_balance - state.balance) / state.session_open_balance >= DAILY_LOSS_LIMIT:
        state.is_halted = True
        state.halt_reason = 'Daily loss limit hit. Stopping for 24h.'
        return False, state.halt_reason
    if state.session_peak_balance and (state.session_peak_balance - state.balance) / state.session_peak_balance >= SESSION_DRAWDOWN_LIMIT:
        return False, 'Session drawdown limit hit. Resuming next session.'
    if state.consecutive_losses >= CONSECUTIVE_LOSS_PAUSE:
        state.halt_until = (datetime.now(timezone.utc) + timedelta(minutes=20)).timestamp()
        state.consecutive_losses = 0
        return False, 'Paused 20 min after consecutive losses.'
    if state.total_trades_7d >= 50 and state.wins_7d / max(state.total_trades_7d, 1) < WEEKLY_WR_MIN:
        state.is_halted = True
        state.halt_reason = 'Weekly WR below threshold. Manual review required.'
        return False, state.halt_reason
    if state.volume_7d_avg and state.hourly_volume < state.volume_7d_avg * VOLUME_MIN_RATIO:
        return False, 'Market volume too low.'
    return True, None
