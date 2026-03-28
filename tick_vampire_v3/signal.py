from tick_vampire_v3.config import (
    DELTA_IMBALANCE_MIN,
    FUNDING_RATE_MAX,
    MICRO_PULLBACK_BARS,
    MIN_SIGNAL_SCORE,
    MOMENTUM_MIN_PCT,
    ORDERBOOK_WEIGHT,
    ORDER_BOOK_LEVELS,
    PRICE_WINDOW,
    RANGE_COMPRESSION_MAX_PCT,
    RANGE_EXPANSION_MIN_PCT,
    RECLAIM_THRESHOLD_PCT,
    ROUND_NUMBER_BUFFER,
    RSI_LONG_MAX,
    RSI_LONG_MIN,
    RSI_SHORT_MAX,
    RSI_SHORT_MIN,
    SPREAD_MAX_PCT,
    TREND_CONFIRM_BARS,
    VOLUME_MIN_RATIO,
)


def simple_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(-period, 0):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period if sum(losses) else 1e-9
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _orderbook_bias(orderbook):
    bids = orderbook.get('bids', [])[:ORDER_BOOK_LEVELS]
    asks = orderbook.get('asks', [])[:ORDER_BOOK_LEVELS]
    bid_volume = sum(size for _, size in bids)
    ask_volume = sum(size for _, size in asks)
    if bid_volume <= 0 or ask_volume <= 0:
        return None, 0.0
    long_ratio = bid_volume / ask_volume
    short_ratio = ask_volume / bid_volume
    if long_ratio >= DELTA_IMBALANCE_MIN:
        return 'LONG', long_ratio
    if short_ratio >= DELTA_IMBALANCE_MIN:
        return 'SHORT', short_ratio
    return None, max(long_ratio, short_ratio)


def _near_round_number(price):
    round_numbers = [1, 10, 100, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 100000]
    return any(abs(price - rn) / max(rn, 1e-9) <= ROUND_NUMBER_BUFFER for rn in round_numbers)


def _trend_ok(values, direction):
    segment = values[-TREND_CONFIRM_BARS:]
    if direction == 'LONG':
        up_steps = sum(1 for i in range(1, len(segment)) if segment[i] >= segment[i - 1])
        return up_steps >= max(1, len(segment) - 1)
    down_steps = sum(1 for i in range(1, len(segment)) if segment[i] <= segment[i - 1])
    return down_steps >= max(1, len(segment) - 1)


def analyze_entry_signal(orderbook, closes, rsi, volume, volume_ma, spread, price, funding_rate):
    if len(closes) < max(PRICE_WINDOW, MICRO_PULLBACK_BARS + TREND_CONFIRM_BARS + 2):
        return {'direction': None, 'reason': 'warmup', 'score': 0.0}

    if spread > SPREAD_MAX_PCT * max(price, 1e-9):
        return {'direction': None, 'reason': 'spread', 'score': 0.0}
    if abs(funding_rate) > FUNDING_RATE_MAX:
        return {'direction': None, 'reason': 'funding', 'score': 0.0}
    if _near_round_number(price):
        return {'direction': None, 'reason': 'round_number', 'score': 0.0}
    if volume < volume_ma * VOLUME_MIN_RATIO:
        return {'direction': None, 'reason': 'volume', 'score': 0.0}

    ob_direction, ob_ratio = _orderbook_bias(orderbook)
    recent = closes[-PRICE_WINDOW:]
    base = recent[0]
    latest = recent[-1]
    swing_low = min(recent)
    swing_high = max(recent)
    total_range_pct = (swing_high - swing_low) / max(base, 1e-9)

    if total_range_pct < RANGE_COMPRESSION_MAX_PCT:
        return {'direction': None, 'reason': 'dead_range', 'score': 0.0}
    if total_range_pct > RANGE_EXPANSION_MIN_PCT * 4.5:
        return {'direction': None, 'reason': 'too_volatile', 'score': 0.0}

    momentum_up = (latest - base) / max(base, 1e-9)
    momentum_down = (base - latest) / max(base, 1e-9)
    last3 = recent[-MICRO_PULLBACK_BARS:]
    volume_score = volume / max(volume_ma, 1e-9)
    orderbook_bonus_long = (ob_ratio / DELTA_IMBALANCE_MIN) * ORDERBOOK_WEIGHT if ob_direction == 'LONG' else 0.0
    orderbook_bonus_short = (ob_ratio / DELTA_IMBALANCE_MIN) * ORDERBOOK_WEIGHT if ob_direction == 'SHORT' else 0.0

    long_pulled_back = last3[0] >= last3[1] <= last3[2]
    long_reclaim_ok = latest >= swing_low * (1 + RECLAIM_THRESHOLD_PCT)
    long_trend_ok = _trend_ok(recent, 'LONG')
    long_rsi_ok = RSI_LONG_MIN <= rsi <= RSI_LONG_MAX
    long_score = (momentum_up / MOMENTUM_MIN_PCT) + volume_score + orderbook_bonus_long + (0.25 if long_trend_ok else 0.0)

    short_pulled_back = last3[0] <= last3[1] >= last3[2]
    short_reclaim_ok = latest <= swing_high * (1 - RECLAIM_THRESHOLD_PCT)
    short_trend_ok = _trend_ok(recent, 'SHORT')
    short_rsi_ok = RSI_SHORT_MIN <= rsi <= RSI_SHORT_MAX
    short_score = (momentum_down / MOMENTUM_MIN_PCT) + volume_score + orderbook_bonus_short + (0.25 if short_trend_ok else 0.0)

    if long_rsi_ok and momentum_up >= MOMENTUM_MIN_PCT and long_pulled_back and long_reclaim_ok and long_trend_ok and long_score >= MIN_SIGNAL_SCORE:
        return {'direction': 'LONG', 'reason': 'momentum_pullback_long', 'score': long_score}
    if short_rsi_ok and momentum_down >= MOMENTUM_MIN_PCT and short_pulled_back and short_reclaim_ok and short_trend_ok and short_score >= MIN_SIGNAL_SCORE:
        return {'direction': 'SHORT', 'reason': 'momentum_pullback_short', 'score': short_score}

    best_score = max(long_score, short_score)
    if best_score < MIN_SIGNAL_SCORE:
        return {'direction': None, 'reason': 'score_too_low', 'score': best_score}
    return {'direction': None, 'reason': 'setup_incomplete', 'score': best_score}
