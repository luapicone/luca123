from reversion_scalp_v1.config import (
    ATR_MAX_PCT,
    ATR_MIN_PCT,
    ATR_PERIOD,
    BB_PERIOD,
    BB_STD,
    MIN_RECLAIM_FRACTION,
    MIN_REVERSAL_BODY_ATR,
    RSI_LONG_MAX,
    RSI_PERIOD,
    RSI_SHORT_MIN,
    SCORE_MIN_THRESHOLD,
    SHORT_CONTINUATION_BLOCK_ATR,
    SHORT_CONTINUATION_BLOCK_RECLAIM,
    SL_ATR_MULTIPLIER,
    SL_PCT_MAX,
    SOL_SCORE_THRESHOLD,
    SOL_SHORT_SCORE_THRESHOLD,
    TP_ATR_MULTIPLIER,
    TP_PCT_MAX,
    VWAP_STRETCH_MIN,
    XRP_SCORE_THRESHOLD,
    Z_SCORE_MIN,
)
from reversion_scalp_v1.indicators import atr, bollinger_bands, rsi, vwap


SYMBOL_SCORE_THRESHOLDS = {
    'SOL/USDT:USDT': SOL_SCORE_THRESHOLD,
    'XRP/USDT:USDT': XRP_SCORE_THRESHOLD,
}


def detect_reversion_signal(candles_5m, candles_15m, symbol=None):
    if len(candles_5m) < max(BB_PERIOD + 5, ATR_PERIOD + 5) or len(candles_15m) < RSI_PERIOD + 5:
        return {'rejected': 'insufficient_history'}

    closes_5m = [c[4] for c in candles_5m]
    closes_15m = [c[4] for c in candles_15m]
    current = closes_5m[-1]
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

    body = abs(current_candle[4] - current_candle[1])
    candle_body_atr = body / max(atr_value, 1e-9)
    candle_range = max(current_candle[2] - current_candle[3], 1e-9)
    long_reclaim = (current_candle[4] - current_candle[3]) / candle_range
    short_reclaim = (current_candle[2] - current_candle[4]) / candle_range
    upper_wick_atr = (current_candle[2] - max(current_candle[1], current_candle[4])) / max(atr_value, 1e-9)

    long_reversal_candle = (
        current_candle[4] > current_candle[1]
        and current_candle[4] >= prev_candle[4]
        and long_reclaim >= MIN_RECLAIM_FRACTION
        and candle_body_atr >= MIN_REVERSAL_BODY_ATR
    )
    short_reversal_candle = (
        current_candle[4] < current_candle[1]
        and current_candle[4] <= prev_candle[4]
        and short_reclaim >= MIN_RECLAIM_FRACTION
        and candle_body_atr >= MIN_REVERSAL_BODY_ATR
    )

    short_continuation_risk = (
        current_candle[4] >= prev_candle[4]
        or short_reclaim < SHORT_CONTINUATION_BLOCK_RECLAIM
        or upper_wick_atr < SHORT_CONTINUATION_BLOCK_ATR
    )

    direction = None
    if intrabar_rsi is not None and context_rsi is not None:
        if intrabar_rsi <= RSI_LONG_MAX and context_rsi <= 48 and stretch <= -VWAP_STRETCH_MIN and zscore <= -Z_SCORE_MIN and long_reversal_candle:
            direction = 'LONG'
        elif intrabar_rsi >= RSI_SHORT_MIN and context_rsi >= 52 and stretch >= VWAP_STRETCH_MIN and zscore >= Z_SCORE_MIN and short_reversal_candle and not short_continuation_risk:
            direction = 'SHORT'

    if direction is None:
        return {
            'rejected': 'no_reversion_setup',
            'rsi_5m': intrabar_rsi,
            'context_rsi': context_rsi,
            'stretch': stretch,
            'zscore': zscore,
            'body_atr': candle_body_atr,
            'long_reclaim': long_reclaim,
            'short_reclaim': short_reclaim,
            'upper_wick_atr': upper_wick_atr,
            'short_continuation_risk': short_continuation_risk,
        }

    if direction == 'LONG':
        sl = current - min(atr_value * SL_ATR_MULTIPLIER, current * SL_PCT_MAX)
        tp = current + min(atr_value * TP_ATR_MULTIPLIER, current * TP_PCT_MAX)
        candle_quality = min(max(current_candle[4] - min(current_candle[3], prev_candle[3]), 0.0) / max(atr_value, 1e-9), 1.5) / 1.5
        context_edge = min((50 - context_rsi) / 20.0, 1.0)
        stretch_edge = min(abs(stretch) / (VWAP_STRETCH_MIN * 2), 1.0)
        reclaim_quality = min(long_reclaim / max(MIN_RECLAIM_FRACTION, 1e-9), 1.5) / 1.5
    else:
        sl = current + min(atr_value * SL_ATR_MULTIPLIER, current * SL_PCT_MAX)
        tp = current - min(atr_value * TP_ATR_MULTIPLIER, current * TP_PCT_MAX)
        candle_quality = min(max(max(current_candle[2], prev_candle[2]) - current_candle[4], 0.0) / max(atr_value, 1e-9), 1.5) / 1.5
        context_edge = min((context_rsi - 50) / 20.0, 1.0)
        stretch_edge = min(abs(stretch) / (VWAP_STRETCH_MIN * 2), 1.0)
        reclaim_quality = min(short_reclaim / max(MIN_RECLAIM_FRACTION, 1e-9), 1.5) / 1.5

    mean_reclaim = min(abs(current - mid) / max(atr_value, 1e-9), 1.5) / 1.5
    score = (
        0.24 * stretch_edge
        + 0.20 * context_edge
        + 0.18 * candle_quality
        + 0.14 * mean_reclaim
        + 0.12 * reclaim_quality
        + 0.12 * min(abs(zscore) / max(Z_SCORE_MIN, 1e-9), 1.5) / 1.5
    )
    symbol_threshold = SYMBOL_SCORE_THRESHOLDS.get(symbol, SCORE_MIN_THRESHOLD)
    if direction == 'SHORT' and symbol == 'SOL/USDT:USDT':
        symbol_threshold = max(symbol_threshold, SOL_SHORT_SCORE_THRESHOLD)
    if score < symbol_threshold:
        return {'rejected': 'score_below_threshold', 'score': score, 'symbol_threshold': symbol_threshold}

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
        'reclaim_quality': reclaim_quality,
        'body_atr': candle_body_atr,
        'upper_wick_atr': upper_wick_atr,
    }
