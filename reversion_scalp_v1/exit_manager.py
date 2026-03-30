from reversion_scalp_v1.config import BE_TRIGGER_PCT, MAX_HOLD_MINUTES, TRAILING_ACTIVATION_PCT, TRAILING_DISTANCE_ATR, FAST_FAIL_MINUTES, MIN_PROGRESS_FOR_HOLD, SCRATCH_EXIT_PCT


def manage_exit(trade, current_price, current_candle, minutes_elapsed, rsi_5m):
    high = current_candle[2]
    low = current_candle[3]
    if trade['direction'] == 'LONG':
        trade['max_price'] = max(trade['max_price'], high)
        progress = (trade['max_price'] - trade['entry']) / max(trade['tp'] - trade['entry'], 1e-9)
        trade['peak_progress'] = max(trade.get('peak_progress', 0.0), progress)
        trade['mfe'] = max(trade.get('mfe', 0.0), trade['max_price'] - trade['entry'])
        trade['mae'] = max(trade.get('mae', 0.0), trade['entry'] - low)
        if low <= trade['sl']:
            return trade['sl'], 'SL', True
        if high >= trade['tp'] and not trade.get('trailing_active'):
            return trade['tp'], 'TP', True
        if not trade['moved_to_be'] and progress >= BE_TRIGGER_PCT:
            trade['sl'] = max(trade['sl'], trade['entry'] + (trade['atr'] * 0.08))
            trade['moved_to_be'] = True
        if progress >= TRAILING_ACTIVATION_PCT:
            trade['trailing_active'] = True
            trail = trade['max_price'] - (trade['atr'] * TRAILING_DISTANCE_ATR)
            trade['sl'] = max(trade['sl'], trail)
        retrace = (trade['max_price'] - current_price) / max(trade['max_price'] - trade['entry'], 1e-9) if trade['max_price'] > trade['entry'] else 0.0
        if progress >= 0.55 and retrace >= 0.35:
            return current_price, 'GIVEBACK_EXIT', True
        if minutes_elapsed >= FAST_FAIL_MINUTES and progress < MIN_PROGRESS_FOR_HOLD and current_price <= trade['entry'] * (1 + SCRATCH_EXIT_PCT):
            return current_price, 'NO_EXPANSION', True
        if minutes_elapsed >= 8 and retrace >= 0.28 and rsi_5m < 50:
            return current_price, 'MOMENTUM_DECAY', True
    else:
        trade['min_price'] = min(trade['min_price'], low)
        progress = (trade['entry'] - trade['min_price']) / max(trade['entry'] - trade['tp'], 1e-9)
        trade['peak_progress'] = max(trade.get('peak_progress', 0.0), progress)
        trade['mfe'] = max(trade.get('mfe', 0.0), trade['entry'] - trade['min_price'])
        trade['mae'] = max(trade.get('mae', 0.0), high - trade['entry'])
        if high >= trade['sl']:
            return trade['sl'], 'SL', True
        if low <= trade['tp'] and not trade.get('trailing_active'):
            return trade['tp'], 'TP', True
        if not trade['moved_to_be'] and progress >= BE_TRIGGER_PCT:
            trade['sl'] = min(trade['sl'], trade['entry'] - (trade['atr'] * 0.08))
            trade['moved_to_be'] = True
        if progress >= TRAILING_ACTIVATION_PCT:
            trade['trailing_active'] = True
            trail = trade['min_price'] + (trade['atr'] * TRAILING_DISTANCE_ATR)
            trade['sl'] = min(trade['sl'], trail)
        retrace = (current_price - trade['min_price']) / max(trade['entry'] - trade['min_price'], 1e-9) if trade['min_price'] < trade['entry'] else 0.0
        if progress >= 0.55 and retrace >= 0.35:
            return current_price, 'GIVEBACK_EXIT', True
        if minutes_elapsed >= FAST_FAIL_MINUTES and progress < MIN_PROGRESS_FOR_HOLD and current_price >= trade['entry'] * (1 - SCRATCH_EXIT_PCT):
            return current_price, 'NO_EXPANSION', True
        if minutes_elapsed >= 8 and retrace >= 0.28 and rsi_5m > 50:
            return current_price, 'MOMENTUM_DECAY', True
    if minutes_elapsed >= MAX_HOLD_MINUTES:
        return current_price, 'TIME', True
    return current_price, 'HOLD', False
