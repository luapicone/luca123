from intradia_selectivo_v1.config import (
    ATR_MAX_PCT,
    ATR_MIN_PCT,
    ATR_PERIOD,
    EMA_FAST,
    EMA_SLOW,
    MAX_PULLBACK_PCT,
    MIN_RECLAIM_BODY_PCT,
    MOMENTUM_MIN_PCT,
    PULLBACK_LOOKBACK,
    RSI_LONG_MIN,
    REGIME_NEUTRAL_RSI_MAX,
    REGIME_NEUTRAL_RSI_MIN,
    RSI_PERIOD,
    RSI_SHORT_MAX,
    ALLOW_LONGS,
    ALLOW_SHORTS,
    SCORE_MIN_THRESHOLD,
    SL_ATR_MULTIPLIER,
    SL_PCT_MAX,
    TP_ATR_MULTIPLIER,
    TP_PCT_MAX,
)
from intradia_selectivo_v1.indicators import atr, ema, rsi


def detect_intraday_signal(candles_15m, candles_1h):
    if len(candles_15m) < max(EMA_SLOW + 5, ATR_PERIOD + 5, PULLBACK_LOOKBACK + 3) or len(candles_1h) < EMA_SLOW + 5:
        return {'rejected': 'insufficient_history'}

    closes_15m = [c[4] for c in candles_15m]
    closes_1h = [c[4] for c in candles_1h]
    current = closes_15m[-1]
    prev = closes_15m[-2]

    atr_value = atr(candles_15m, ATR_PERIOD)
    if not atr_value:
        return {'rejected': 'atr_unavailable'}
    atr_pct = atr_value / max(current, 1e-9)
    if atr_pct < ATR_MIN_PCT or atr_pct > ATR_MAX_PCT:
        return {'rejected': 'atr_regime', 'atr_pct': atr_pct}

    ema_fast_15m = ema(closes_15m, EMA_FAST)
    ema_slow_15m = ema(closes_15m, EMA_SLOW)
    ema_fast_1h = ema(closes_1h, EMA_FAST)
    ema_slow_1h = ema(closes_1h, EMA_SLOW)
    if None in (ema_fast_15m, ema_slow_15m, ema_fast_1h, ema_slow_1h):
        return {'rejected': 'ema_unavailable'}

    context_rsi = rsi(closes_1h, RSI_PERIOD)
    entry_rsi = rsi(closes_15m, RSI_PERIOD)

    regime_neutral = REGIME_NEUTRAL_RSI_MIN <= context_rsi <= REGIME_NEUTRAL_RSI_MAX
    bullish_context = ALLOW_LONGS and ema_fast_1h > ema_slow_1h and context_rsi >= RSI_LONG_MIN
    bearish_context = ALLOW_SHORTS and ema_fast_1h < ema_slow_1h and context_rsi <= RSI_SHORT_MAX

    impulse_ref = closes_15m[-(PULLBACK_LOOKBACK + 2)]
    momentum_pct = (current - impulse_ref) / max(impulse_ref, 1e-9)
    recent_high = max(c[2] for c in candles_15m[-(PULLBACK_LOOKBACK + 1):-1])
    recent_low = min(c[3] for c in candles_15m[-(PULLBACK_LOOKBACK + 1):-1])
    pullback_pct = (recent_high - current) / max(recent_high, 1e-9)
    reclaim_body_pct = abs(current - candles_15m[-1][1]) / max(current, 1e-9)

    direction = None
    short_pullback_pct = (current - recent_low) / max(current, 1e-9)
    if bullish_context and ema_fast_15m > ema_slow_15m and momentum_pct >= MOMENTUM_MIN_PCT and pullback_pct <= MAX_PULLBACK_PCT and current > prev and reclaim_body_pct >= MIN_RECLAIM_BODY_PCT:
        direction = 'LONG'
    elif bearish_context and ema_fast_15m < ema_slow_15m and momentum_pct <= -MOMENTUM_MIN_PCT and short_pullback_pct <= MAX_PULLBACK_PCT and current < prev and reclaim_body_pct >= MIN_RECLAIM_BODY_PCT:
        direction = 'SHORT'

    if direction is None:
        return {
            'rejected': 'no_intraday_setup',
            'momentum_pct': momentum_pct,
            'context_rsi': context_rsi,
            'entry_rsi': entry_rsi,
            'pullback_pct': pullback_pct,
            'short_pullback_pct': short_pullback_pct,
            'regime_neutral': regime_neutral,
        }

    if direction == 'LONG':
        sl = current - min(atr_value * SL_ATR_MULTIPLIER, current * SL_PCT_MAX)
        tp = current + min(atr_value * TP_ATR_MULTIPLIER, current * TP_PCT_MAX)
        trend_edge = min((ema_fast_1h - ema_slow_1h) / max(current * 0.002, 1e-9), 1.5) / 1.5
        rsi_edge = min((context_rsi - 50) / 20.0, 1.0)
    else:
        sl = current + min(atr_value * SL_ATR_MULTIPLIER, current * SL_PCT_MAX)
        tp = current - min(atr_value * TP_ATR_MULTIPLIER, current * TP_PCT_MAX)
        trend_edge = min((ema_slow_1h - ema_fast_1h) / max(current * 0.002, 1e-9), 1.5) / 1.5
        rsi_edge = min((50 - context_rsi) / 20.0, 1.0)

    momentum_edge = min(abs(momentum_pct) / MOMENTUM_MIN_PCT, 2.0) / 2.0
    reclaim_edge = min(reclaim_body_pct / MIN_RECLAIM_BODY_PCT, 2.0) / 2.0
    active_pullback_pct = pullback_pct if direction == 'LONG' else short_pullback_pct
    pullback_quality = max(0.0, 1.0 - (active_pullback_pct / max(MAX_PULLBACK_PCT, 1e-9)))
    score = 0.28 * trend_edge + 0.24 * momentum_edge + 0.18 * reclaim_edge + 0.18 * pullback_quality + 0.12 * rsi_edge
    if score < SCORE_MIN_THRESHOLD:
        return {'rejected': 'score_below_threshold', 'score': score}

    return {
        'direction': direction,
        'entry': current,
        'sl': sl,
        'tp': tp,
        'atr': atr_value,
        'score': score,
        'momentum_pct': momentum_pct,
        'context_rsi': context_rsi,
        'pullback_pct': active_pullback_pct,
    }
