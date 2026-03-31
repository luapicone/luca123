from reversion_scalp_v1.config import (
    BE_TRIGGER_PCT,
    FAST_FAIL_MINUTES,
    GIVEBACK_EXIT_PROGRESS,
    GIVEBACK_EXIT_RETRACE,
    MAX_HOLD_MINUTES,
    MICRO_PARTIAL_LOCK_ATR,
    MICRO_PARTIAL_TRIGGER_PCT,
    MIN_PROGRESS_FOR_HOLD,
    MOMENTUM_DECAY_MINUTES,
    MOMENTUM_DECAY_RETRACE,
    SCRATCH_EXIT_PCT,
    TRAILING_ACTIVATION_PCT,
    TRAILING_DISTANCE_ATR,
)


def _net_room(trade, current_price):
    size = trade.get('remaining_size', trade['size'])
    if trade['direction'] == 'LONG':
        return (current_price - trade['entry']) * size
    return (trade['entry'] - current_price) * size


def _partial_lock_sl(trade):
    if trade['direction'] == 'LONG':
        return trade['entry'] + (trade['atr'] * MICRO_PARTIAL_LOCK_ATR)
    return trade['entry'] - (trade['atr'] * MICRO_PARTIAL_LOCK_ATR)


def _maybe_take_partial(trade, current_price, progress):
    if trade.get('partial_taken'):
        return None
    partial_size = min(trade.get('partial_size', 0.0), trade.get('remaining_size', trade['size']))
    if partial_size <= 0:
        trade['partial_taken'] = True
        return None
    if progress < MICRO_PARTIAL_TRIGGER_PCT:
        return None

    if trade['direction'] == 'LONG':
        realized = (current_price - trade['entry']) * partial_size
        trade['sl'] = max(trade['sl'], _partial_lock_sl(trade))
    else:
        realized = (trade['entry'] - current_price) * partial_size
        trade['sl'] = min(trade['sl'], _partial_lock_sl(trade))

    trade['partial_taken'] = True
    trade['remaining_size'] = round(max(trade.get('remaining_size', trade['size']) - partial_size, 0.0), 3)
    trade['realized_partial_pnl'] = trade.get('realized_partial_pnl', 0.0) + realized
    trade['moved_to_be'] = True
    return partial_size, realized


def manage_exit(trade, current_price, current_candle, minutes_elapsed, rsi_5m):
    high = current_candle[2]
    low = current_candle[3]
    trade.setdefault('remaining_size', trade['size'])
    trade.setdefault('realized_partial_pnl', 0.0)
    trade.setdefault('partial_taken', False)

    if trade['direction'] == 'LONG':
        trade['max_price'] = max(trade['max_price'], high)
        progress = (trade['max_price'] - trade['entry']) / max(trade['tp'] - trade['entry'], 1e-9)
        trade['peak_progress'] = max(trade.get('peak_progress', 0.0), progress)
        trade['mfe'] = max(trade.get('mfe', 0.0), trade['max_price'] - trade['entry'])
        trade['mae'] = max(trade.get('mae', 0.0), trade['entry'] - low)

        partial = _maybe_take_partial(trade, current_price, progress)
        if low <= trade['sl']:
            return trade['sl'], 'SL', True, partial
        if high >= trade['tp'] and not trade.get('trailing_active'):
            return trade['tp'], 'TP', True, partial
        if not trade['moved_to_be'] and progress >= BE_TRIGGER_PCT:
            trade['sl'] = max(trade['sl'], trade['entry'] + (trade['atr'] * 0.10))
            trade['moved_to_be'] = True
        if progress >= TRAILING_ACTIVATION_PCT:
            trade['trailing_active'] = True
            trail = trade['max_price'] - (trade['atr'] * TRAILING_DISTANCE_ATR)
            trade['sl'] = max(trade['sl'], trail)
        retrace = (trade['max_price'] - current_price) / max(trade['max_price'] - trade['entry'], 1e-9) if trade['max_price'] > trade['entry'] else 0.0
        gross_buffer = trade['fee'] * 1.15
        if progress >= GIVEBACK_EXIT_PROGRESS and retrace >= GIVEBACK_EXIT_RETRACE and _net_room(trade, current_price) > gross_buffer:
            return current_price, 'GIVEBACK_EXIT', True, partial
        if minutes_elapsed >= FAST_FAIL_MINUTES and progress < MIN_PROGRESS_FOR_HOLD and current_price <= trade['entry'] * (1 + SCRATCH_EXIT_PCT):
            return current_price, 'NO_EXPANSION', True, partial
        if minutes_elapsed >= MOMENTUM_DECAY_MINUTES and retrace >= MOMENTUM_DECAY_RETRACE and rsi_5m < 50:
            return current_price, 'MOMENTUM_DECAY', True, partial
    else:
        trade['min_price'] = min(trade['min_price'], low)
        progress = (trade['entry'] - trade['min_price']) / max(trade['entry'] - trade['tp'], 1e-9)
        trade['peak_progress'] = max(trade.get('peak_progress', 0.0), progress)
        trade['mfe'] = max(trade.get('mfe', 0.0), trade['entry'] - trade['min_price'])
        trade['mae'] = max(trade.get('mae', 0.0), high - trade['entry'])

        partial = _maybe_take_partial(trade, current_price, progress)
        if high >= trade['sl']:
            return trade['sl'], 'SL', True, partial
        if low <= trade['tp'] and not trade.get('trailing_active'):
            return trade['tp'], 'TP', True, partial
        if not trade['moved_to_be'] and progress >= BE_TRIGGER_PCT:
            trade['sl'] = min(trade['sl'], trade['entry'] - (trade['atr'] * 0.10))
            trade['moved_to_be'] = True
        if progress >= TRAILING_ACTIVATION_PCT:
            trade['trailing_active'] = True
            trail = trade['min_price'] + (trade['atr'] * TRAILING_DISTANCE_ATR)
            trade['sl'] = min(trade['sl'], trail)
        retrace = (current_price - trade['min_price']) / max(trade['entry'] - trade['min_price'], 1e-9) if trade['min_price'] < trade['entry'] else 0.0
        gross_buffer = trade['fee'] * 1.15
        if progress >= GIVEBACK_EXIT_PROGRESS and retrace >= GIVEBACK_EXIT_RETRACE and _net_room(trade, current_price) > gross_buffer:
            return current_price, 'GIVEBACK_EXIT', True, partial
        if minutes_elapsed >= FAST_FAIL_MINUTES and progress < MIN_PROGRESS_FOR_HOLD and current_price >= trade['entry'] * (1 - SCRATCH_EXIT_PCT):
            return current_price, 'NO_EXPANSION', True, partial
        if minutes_elapsed >= MOMENTUM_DECAY_MINUTES and retrace >= MOMENTUM_DECAY_RETRACE and rsi_5m > 50:
            return current_price, 'MOMENTUM_DECAY', True, partial

    if minutes_elapsed >= MAX_HOLD_MINUTES:
        return current_price, 'TIME', True, partial
    return current_price, 'HOLD', False, partial
