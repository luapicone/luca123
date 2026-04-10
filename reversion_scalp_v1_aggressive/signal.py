from reversion_scalp_v1_aggressive.config import (
    ATR_MAX_PCT,
    ATR_MIN_PCT,
    ATR_PERIOD,
    BB_PERIOD,
    BB_STD,
    RSI_LONG_MAX,
    RSI_PERIOD,
    RSI_SHORT_MIN,
    RSI_CONTEXT_LONG_MAX,
    RSI_CONTEXT_SHORT_MIN,
    SCORE_FILTER_MAX,
    SCORE_FILTER_MIN,
    SCORE_MIN_THRESHOLD,
    SL_ATR_MULTIPLIER,
    SL_PCT_MAX,
    TP_ATR_MULTIPLIER,
    TP_PCT_MAX,
    VWAP_STRETCH_MIN,
    ZSCORE_FILTER_MAX,
    ZSCORE_FILTER_MIN,
    Z_SCORE_MIN,
)
from reversion_scalp_v1_aggressive.indicators import atr, bollinger_bands, rsi, sma, vwap


def detect_reversion_signal(candles_5m, candles_15m):
    if len(candles_5m) < max(BB_PERIOD + 5, ATR_PERIOD + 5) or len(candles_15m) < RSI_PERIOD + 5:
        return {'rejected': 'insufficient_history'}

    closes_5m = [c[4] for c in candles_5m]
    closes_15m = [c[4] for c in candles_15m]
    current = closes_5m[-1]
    prev = closes_5m[-2]
    current_candle = candles_5m[-1]
    prev_candle = candles_5m[-2]

    atr_value = atr(candles_5m, ATR_PERIOD)
    if not atr_value:
        return {'rejected': 'atr_unavailable'}
    atr_pct = atr_value / max(current, 1e-9)
    if atr_pct < ATR_MIN_PCT or atr_pct > ATR_MAX_PCT:
        return {'rejected': 'atr_regime', 'atr_pct': atr_pct}

    lower, mid, upper = bollinger_bands(closes_5m, BB_PERIOD, BB_STD)
    if lower is None:
        return {'rejected': 'bb_unavailable'}
    band_width = max(upper - lower, 1e-9)
    zscore = (current - mid) / band_width
    intrabar_rsi = rsi(closes_5m, RSI_PERIOD)
    context_rsi = rsi(closes_15m, RSI_PERIOD)
    day_vwap = vwap(candles_5m, 20)
    if day_vwap is None:
        return {'rejected': 'vwap_unavailable'}
    stretch = (current - day_vwap) / max(day_vwap, 1e-9)

    long_reversal_candle = ((current_candle[4] > current_candle[1] and current_candle[4] >= prev_candle[4]) or current_candle[4] > ((current_candle[2] + current_candle[3]) / 2) or current_candle[4] > prev_candle[3])
    short_reversal_candle = ((current_candle[4] < current_candle[1] and current_candle[4] <= prev_candle[4]) or current_candle[4] < ((current_candle[2] + current_candle[3]) / 2) or current_candle[4] < prev_candle[2])

    direction = None
    if intrabar_rsi is not None and context_rsi is not None:
        long_trigger = (long_reversal_candle or (intrabar_rsi <= RSI_LONG_MAX - 2 and stretch <= -(VWAP_STRETCH_MIN * 1.35)))
        short_trigger = (short_reversal_candle or (intrabar_rsi >= RSI_SHORT_MIN + 2 and stretch >= (VWAP_STRETCH_MIN * 1.35)))
        if intrabar_rsi <= RSI_LONG_MAX and context_rsi <= RSI_CONTEXT_LONG_MAX and stretch <= -VWAP_STRETCH_MIN and zscore <= -Z_SCORE_MIN and long_trigger:
            direction = 'LONG'
        elif intrabar_rsi >= RSI_SHORT_MIN and context_rsi >= RSI_CONTEXT_SHORT_MIN and stretch >= VWAP_STRETCH_MIN and zscore >= Z_SCORE_MIN and short_trigger:
            direction = 'SHORT'

    if direction is None:
        return {'rejected': 'no_reversion_setup', 'rsi_5m': intrabar_rsi, 'context_rsi': context_rsi, 'stretch': stretch, 'zscore': zscore}

    if direction == 'LONG':
        sl = current - min(atr_value * SL_ATR_MULTIPLIER, current * SL_PCT_MAX)
        tp = current + min(atr_value * TP_ATR_MULTIPLIER, current * TP_PCT_MAX)
        candle_quality = min(max(current_candle[4] - min(current_candle[3], prev_candle[3]), 0.0) / max(atr_value, 1e-9), 1.5) / 1.5
        context_edge = min((50 - context_rsi) / 20.0, 1.0)
        stretch_edge = min(abs(stretch) / (VWAP_STRETCH_MIN * 2), 1.0)
    else:
        sl = current + min(atr_value * SL_ATR_MULTIPLIER, current * SL_PCT_MAX)
        tp = current - min(atr_value * TP_ATR_MULTIPLIER, current * TP_PCT_MAX)
        candle_quality = min(max(max(current_candle[2], prev_candle[2]) - current_candle[4], 0.0) / max(atr_value, 1e-9), 1.5) / 1.5
        context_edge = min((context_rsi - 50) / 20.0, 1.0)
        stretch_edge = min(abs(stretch) / (VWAP_STRETCH_MIN * 2), 1.0)

    mean_reclaim = min(abs(current - mid) / max(atr_value, 1e-9), 1.5) / 1.5
    score = 0.28 * stretch_edge + 0.22 * context_edge + 0.20 * candle_quality + 0.20 * mean_reclaim + 0.10 * min(abs(zscore) / max(Z_SCORE_MIN, 1e-9), 1.5) / 1.5
    if score < SCORE_MIN_THRESHOLD:
        return {'rejected': 'score_below_threshold', 'score': score}

    abs_zscore = abs(zscore)
    if score < SCORE_FILTER_MIN or score >= SCORE_FILTER_MAX:
        return {'rejected': 'score_filter_window', 'score': score, 'zscore': zscore}
    if abs_zscore < ZSCORE_FILTER_MIN or abs_zscore >= ZSCORE_FILTER_MAX:
        return {'rejected': 'zscore_filter_window', 'score': score, 'zscore': zscore}

    return {
        'direction': direction,
        'entry': current,
        'sl': sl,
        'tp': tp,
        'atr': atr_value,
        'score': score,
        'stretch': stretch,
        'context_rsi': context_rsi,
        'zscore': zscore,
    }
