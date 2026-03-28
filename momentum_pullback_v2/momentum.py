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
        return None

    closes_5m = [c[4] for c in candles_5m]
    volumes_5m = [c[5] for c in candles_5m]
    closes_15m = [c[4] for c in candles_15m]
    current_price = closes_5m[-1]

    atr_value = atr(candles_5m, ATR_PERIOD)
    if not atr_value:
        return None
    atr_pct = atr_value / max(current_price, 1e-9)
    if atr_pct < ATR_MIN_PCT or atr_pct > ATR_MAX_PCT:
        return None

    context_rsi = rsi(closes_15m, 14)

    impulse_start_close = closes_5m[-(MOMENTUM_LOOKBACK + 1)]
    impulse_end_close = closes_5m[-(PULLBACK_MAX_CANDLES + 2)]
    net_move_pct = (impulse_end_close - impulse_start_close) / max(impulse_start_close, 1e-9)
    direction = 'LONG' if net_move_pct >= MOMENTUM_MIN_PCT else 'SHORT' if net_move_pct <= -MOMENTUM_MIN_PCT else None
    if direction is None:
        return None

    if direction == 'LONG' and context_rsi > RSI_LONG_MAX:
        return None
    if direction == 'SHORT' and context_rsi < RSI_SHORT_MIN:
        return None

    pullback_slice = candles_5m[-(PULLBACK_MAX_CANDLES + 1):-1]
    if len(pullback_slice) < PULLBACK_MIN_CANDLES:
        return None

    pullback_len = 0
    for candle in reversed(pullback_slice):
        o, c = candle[1], candle[4]
        if direction == 'LONG' and c <= o:
            pullback_len += 1
        elif direction == 'SHORT' and c >= o:
            pullback_len += 1
        else:
            break
    if pullback_len < PULLBACK_MIN_CANDLES or pullback_len > PULLBACK_MAX_CANDLES:
        return None

    active_pullback = pullback_slice[-pullback_len:]
    impulse_high = max(c[2] for c in candles_5m[-(pullback_len + MOMENTUM_LOOKBACK + 1):-(pullback_len + 1)])
    impulse_low = min(c[3] for c in candles_5m[-(pullback_len + MOMENTUM_LOOKBACK + 1):-(pullback_len + 1)])
    impulse_size = max(impulse_high - impulse_low, 1e-9)
    pullback_low = min(c[3] for c in active_pullback)
    pullback_high = max(c[2] for c in active_pullback)

    if direction == 'LONG':
        retrace = (impulse_high - pullback_low) / impulse_size
        reclaim_ok = candles_5m[-1][4] > active_pullback[-1][2] and candles_5m[-1][4] > candles_5m[-1][1]
        structural_sl = pullback_low - (atr_value * 0.2)
    else:
        retrace = (pullback_high - impulse_low) / impulse_size
        reclaim_ok = candles_5m[-1][4] < active_pullback[-1][3] and candles_5m[-1][4] < candles_5m[-1][1]
        structural_sl = pullback_high + (atr_value * 0.2)

    if retrace > PULLBACK_MAX_DEPTH or not reclaim_ok:
        return None

    vol_ma = sma(volumes_5m[:-1], 20)
    if not vol_ma:
        return None
    impulse_vol = sum(c[5] for c in candles_5m[-(pullback_len + 3):-(pullback_len + 1)]) / 2
    pullback_vol = sum(c[5] for c in active_pullback) / len(active_pullback)
    if impulse_vol < vol_ma * VOLUME_IMPULSE_RATIO:
        return None
    if pullback_vol > vol_ma * VOLUME_PULLBACK_RATIO:
        return None

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
    depth_quality = max(0.0, 1.0 - (retrace / PULLBACK_MAX_DEPTH))
    volume_quality = min((impulse_vol / max(vol_ma, 1e-9)) / VOLUME_IMPULSE_RATIO, 2.0) / 2.0
    reclaim_strength = min(abs(candles_5m[-1][4] - candles_5m[-1][1]) / max(entry * 0.001, 1e-9), 2.0) / 2.0
    score = 0.30 * momentum_strength + 0.25 * depth_quality + 0.25 * volume_quality + 0.20 * reclaim_strength

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
