from reversion_scalp_v1.config import (
    ATR_MAX_PCT,
    ATR_MIN_PCT,
    ATR_PERIOD,
    BB_PERIOD,
    BB_STD,
    RSI_LONG_MAX,
    RSI_PERIOD,
    RSI_SHORT_MIN,
    SCORE_MIN_THRESHOLD,
    SL_ATR_MULTIPLIER,
    SL_PCT_MAX,
    TP_ATR_MULTIPLIER,
    TP_PCT_MAX,
    VWAP_STRETCH_MIN,
    Z_SCORE_MIN,
)
from reversion_scalp_v1.indicators import atr, bollinger_bands, rsi, sma, vwap


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

    long_reversal_candle = current_candle[4] > current_candle[1] and current_candle[4] > prev_candle[4]
    short_reversal_candle = current_candle[4] < current_candle[1] and current_candle[4] < prev_candle[4]

    direction = None
    if intrabar_rsi is not None and context_rsi is not None:
        if intrabar_rsi <= RSI_LONG_MAX and context_rsi <= 48 and stretch <= -VWAP_STRETCH_MIN and zscore <= -Z_SCORE_MIN and long_reversal_candle:
            direction = 'LONG'
        elif intrabar_rsi >= RSI_SHORT_MIN and context_rsi >= 52 and stretch >= VWAP_STRETCH_MIN and zscore >= Z_SCORE_MIN and short_reversal_candle:
            direction = 'SHORT'

    if direction is None:
        return {'rejected': 'no_reversion_setup', 'rsi_5m': intrabar_rsi, 'context_rsi': context_rsi, 'stretch': stretch, 'zscore': zscore}

    if direction == 'LONG':
        sl = current - min(atr_value * SL_ATR_MULTIPLIER, current * SL_PCT_MAX)
        tp = current + min(atr_value * TP_ATR_MULTIPLIER, current * TP_PCT_MAX)
        candle_quality = min((current_candle[4] - current_candle[3]) / max(atr_value, 1e-9), 1.5) / 1.5
        context_edge = min((50 - context_rsi) / 20.0, 1.0)
        stretch_edge = min(abs(stretch) / (VWAP_STRETCH_MIN * 2), 1.0)
    else:
        sl = current + min(atr_value * SL_ATR_MULTIPLIER, current * SL_PCT_MAX)
        tp = current - min(atr_value * TP_ATR_MULTIPLIER, current * TP_PCT_MAX)
        candle_quality = min((current_candle[2] - current_candle[4]) / max(atr_value, 1e-9), 1.5) / 1.5
        context_edge = min((context_rsi - 50) / 20.0, 1.0)
        stretch_edge = min(abs(stretch) / (VWAP_STRETCH_MIN * 2), 1.0)

    mean_reclaim = min(abs(current - mid) / max(atr_value, 1e-9), 1.5) / 1.5
    score = 0.30 * stretch_edge + 0.25 * context_edge + 0.20 * candle_quality + 0.25 * mean_reclaim
    if score < SCORE_MIN_THRESHOLD:
        return {'rejected': 'score_below_threshold', 'score': score}

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
