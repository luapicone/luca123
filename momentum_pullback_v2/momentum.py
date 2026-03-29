from momentum_pullback_v2.config import (
    ATR_PERIOD,
    ATR_SL_MULTIPLIER,
    ATR_TP_MULTIPLIER,
    MOMENTUM_LOOKBACK,
    MOMENTUM_MIN_PCT,
    PULLBACK_MAX_CANDLES,
    PULLBACK_MAX_DEPTH,
    PULLBACK_MIN_CANDLES,
    RSI_LONG_MAX,
    RSI_SHORT_MIN,
    SL_PCT_MAX,
    SL_PCT_MIN,
    TP_RATIO,
    VOLUME_IMPULSE_RATIO,
    VOLUME_PULLBACK_RATIO,
    ATR_MIN_PCT,
    ATR_MAX_PCT,
)
from momentum_pullback_v2.indicators import atr, rsi, sma


def detect_momentum_pullback(candles_5m, candles_15m):
    if len(candles_5m) < MOMENTUM_LOOKBACK + PULLBACK_MAX_CANDLES + 3 or len(candles_15m) < ATR_PERIOD + 5:
        return {'rejected': 'insufficient_history'}

    closes_5m = [c[4] for c in candles_5m]
    volumes_5m = [c[5] for c in candles_5m]
    closes_15m = [c[4] for c in candles_15m]
    current_price = closes_5m[-1]

    atr_value = atr(candles_5m, ATR_PERIOD)
    if not atr_value:
        return {'rejected': 'atr_unavailable'}
    atr_pct = atr_value / max(current_price, 1e-9)
    if atr_pct < ATR_MIN_PCT or atr_pct > ATR_MAX_PCT:
        return {'rejected': 'atr_regime', 'atr_pct': atr_pct}

    context_rsi = rsi(closes_15m, 14)

    impulse_start_close = closes_5m[-(MOMENTUM_LOOKBACK + 1)]
    impulse_end_close = closes_5m[-(PULLBACK_MAX_CANDLES + 2)]
    net_move_pct = (impulse_end_close - impulse_start_close) / max(impulse_start_close, 1e-9)
    direction = 'LONG' if net_move_pct >= MOMENTUM_MIN_PCT else 'SHORT' if net_move_pct <= -MOMENTUM_MIN_PCT else None
    if direction is None:
        return {'rejected': 'momentum_missing', 'momentum_pct': net_move_pct}

    if direction == 'LONG' and context_rsi > RSI_LONG_MAX:
        return {'rejected': 'context_rsi_long', 'context_rsi': context_rsi}
    if direction == 'SHORT' and context_rsi < RSI_SHORT_MIN:
        return {'rejected': 'context_rsi_short', 'context_rsi': context_rsi}
    if direction == 'LONG' and candles_15m[-1][4] < candles_15m[-1][1]:
        return {'rejected': 'context_candle_against_long'}
    if direction == 'SHORT' and candles_15m[-1][4] > candles_15m[-1][1]:
        return {'rejected': 'context_candle_against_short'}

    pullback_slice = candles_5m[-(PULLBACK_MAX_CANDLES + 1):-1]
    if len(pullback_slice) < PULLBACK_MIN_CANDLES:
        return {'rejected': 'pullback_slice_short'}

    pullback_len = 0
    for candle in reversed(pullback_slice):
        o, c = candle[1], candle[4]
        if direction == 'LONG' and c <= o:
            pullback_len += 1
        elif direction == 'SHORT' and c >= o:
            pullback_len += 1
        else:
            break
    if pullback_len == 0:
        candidate = pullback_slice[-1]
        candidate_mid = (candidate[2] + candidate[3]) / 2
        if direction == 'LONG' and candidate[4] < candidate_mid:
            pullback_len = 1
        elif direction == 'SHORT' and candidate[4] > candidate_mid:
            pullback_len = 1
    if pullback_len < PULLBACK_MIN_CANDLES or pullback_len > PULLBACK_MAX_CANDLES:
        return {'rejected': 'pullback_len', 'pullback_len': pullback_len}

    active_pullback = pullback_slice[-pullback_len:]
    impulse_high = max(c[2] for c in candles_5m[-(pullback_len + MOMENTUM_LOOKBACK + 1):-(pullback_len + 1)])
    impulse_low = min(c[3] for c in candles_5m[-(pullback_len + MOMENTUM_LOOKBACK + 1):-(pullback_len + 1)])
    impulse_size = max(impulse_high - impulse_low, 1e-9)
    pullback_low = min(c[3] for c in active_pullback)
    pullback_high = max(c[2] for c in active_pullback)

    if direction == 'LONG':
        retrace = (impulse_high - pullback_low) / impulse_size
        reclaim_ok = candles_5m[-1][4] > candles_5m[-1][1] or candles_5m[-1][4] >= ((active_pullback[-1][2] + active_pullback[-1][4]) / 2)
        structural_sl = pullback_low - (atr_value * 0.2)
    else:
        retrace = (pullback_high - impulse_low) / impulse_size
        reclaim_ok = candles_5m[-1][4] < candles_5m[-1][1] or candles_5m[-1][4] <= ((active_pullback[-1][3] + active_pullback[-1][4]) / 2)
        structural_sl = pullback_high + (atr_value * 0.2)

    trend_strength = min(abs(net_move_pct) / max(MOMENTUM_MIN_PCT, 1e-9), 2.0) / 2.0
    adaptive_retrace_limit = PULLBACK_MAX_DEPTH + (0.08 if trend_strength >= 0.6 else 0.03)
    reclaim_override = pullback_len == 1 and retrace <= adaptive_retrace_limit * 0.55
    if retrace > adaptive_retrace_limit or (not reclaim_ok and not reclaim_override):
        return {'rejected': 'pullback_retrace_or_reclaim', 'retrace': retrace, 'reclaim_ok': reclaim_ok}

    vol_ma = sma(volumes_5m[:-1], 20)
    if not vol_ma:
        return {'rejected': 'volume_ma_unavailable'}
    impulse_vol = sum(c[5] for c in candles_5m[-(pullback_len + 3):-(pullback_len + 1)]) / 2
    pullback_vol = sum(c[5] for c in active_pullback) / len(active_pullback)
    volume_floor = vol_ma * VOLUME_IMPULSE_RATIO
    if impulse_vol < volume_floor * 0.97:
        return {'rejected': 'impulse_volume_low', 'impulse_vol': impulse_vol, 'vol_ma': vol_ma}
    if pullback_vol > vol_ma * VOLUME_PULLBACK_RATIO:
        return {'rejected': 'pullback_volume_high', 'pullback_vol': pullback_vol, 'vol_ma': vol_ma}

    entry = candles_5m[-1][4]
    atr_sl = atr_value * ATR_SL_MULTIPLIER
    if direction == 'LONG':
        sl_distance = min(max(entry - structural_sl, entry * SL_PCT_MIN), entry * SL_PCT_MAX)
        sl_distance = min(max(sl_distance, atr_sl), entry * SL_PCT_MAX)
        sl = entry - sl_distance
        tp = entry + max(atr_value * ATR_TP_MULTIPLIER, sl_distance * TP_RATIO)
    else:
        sl_distance = min(max(structural_sl - entry, entry * SL_PCT_MIN), entry * SL_PCT_MAX)
        sl_distance = min(max(sl_distance, atr_sl), entry * SL_PCT_MAX)
        sl = entry + sl_distance
        tp = entry - max(atr_value * ATR_TP_MULTIPLIER, sl_distance * TP_RATIO)

    momentum_strength = min(abs(net_move_pct) / MOMENTUM_MIN_PCT, 3.0) / 3.0
    depth_quality = max(0.0, 1.0 - (retrace / max(PULLBACK_MAX_DEPTH, 1e-9)))
    volume_quality = min((impulse_vol / max(vol_ma, 1e-9)) / max(VOLUME_IMPULSE_RATIO, 1e-9), 2.0) / 2.0
    reclaim_strength = min(abs(candles_5m[-1][4] - candles_5m[-1][1]) / max(entry * 0.001, 1e-9), 2.0) / 2.0
    rsi_edge = min(abs(context_rsi - 50.0) / 15.0, 1.0)
    structure_bonus = 0.10 if pullback_len <= 2 else 0.0
    score = 0.22 * momentum_strength + 0.18 * depth_quality + 0.15 * volume_quality + 0.15 * reclaim_strength + 0.20 * rsi_edge + structure_bonus

    return {
        'direction': direction,
        'entry': entry,
        'sl': sl,
        'tp': tp,
        'atr': atr_value,
        'score': score,
        'context_rsi': context_rsi,
        'retrace': retrace,
        'momentum_pct': net_move_pct,
        'pullback_len': pullback_len,
    }
