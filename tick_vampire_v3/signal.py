from tick_vampire_v3.config import (
    DELTA_IMBALANCE_MIN,
    FUNDING_RATE_MAX,
    MICRO_PULLBACK_BARS,
    MOMENTUM_MIN_PCT,
    ORDER_BOOK_LEVELS,
    PRICE_WINDOW,
    RECLAIM_THRESHOLD_PCT,
    ROUND_NUMBER_BUFFER,
    RSI_MAX,
    RSI_MIN,
    SPREAD_MAX_PCT,
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
        return None, bid_volume, ask_volume
    ratio = bid_volume / ask_volume
    if ratio >= DELTA_IMBALANCE_MIN:
        return 'LONG', bid_volume, ask_volume
    if (ask_volume / bid_volume) >= DELTA_IMBALANCE_MIN:
        return 'SHORT', bid_volume, ask_volume
    return None, bid_volume, ask_volume


def _near_round_number(price):
    round_numbers = [1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000]
    return any(abs(price - rn) / rn <= ROUND_NUMBER_BUFFER for rn in round_numbers)


def analyze_entry_signal(orderbook, closes, rsi, volume, volume_ma, spread, price, funding_rate):
    if len(closes) < max(PRICE_WINDOW, MICRO_PULLBACK_BARS + 3):
        return {'direction': None, 'reason': 'warmup'}

    spread_ok = spread <= SPREAD_MAX_PCT * max(price, 1e-9)
    funding_ok = abs(funding_rate) <= FUNDING_RATE_MAX
    volume_ok = volume >= volume_ma
    rsi_mid_ok = RSI_MIN <= rsi <= RSI_MAX
    round_ok = not _near_round_number(price)
    ob_direction, bid_volume, ask_volume = _orderbook_bias(orderbook)
    if not spread_ok:
        return {'direction': None, 'reason': 'spread'}
    if not funding_ok:
        return {'direction': None, 'reason': 'funding'}
    if not volume_ok:
        return {'direction': None, 'reason': 'volume'}
    if not round_ok:
        return {'direction': None, 'reason': 'round_number'}
    if not rsi_mid_ok:
        return {'direction': None, 'reason': 'rsi_range'}
    if ob_direction is None:
        return {'direction': None, 'reason': 'orderbook_neutral'}

    recent = closes[-PRICE_WINDOW:]
    base = recent[0]
    latest = recent[-1]
    swing_low = min(recent)
    swing_high = max(recent)
    momentum_up = (latest - base) / max(base, 1e-9)
    momentum_down = (base - latest) / max(base, 1e-9)
    last3 = recent[-MICRO_PULLBACK_BARS:]

    if ob_direction == 'LONG':
        pulled_back = last3[0] >= last3[1] <= last3[2]
        reclaim_ok = latest >= swing_low * (1 + RECLAIM_THRESHOLD_PCT)
        if momentum_up >= MOMENTUM_MIN_PCT and pulled_back and reclaim_ok:
            return {
                'direction': 'LONG',
                'reason': 'micro_pullback_long',
                'momentum_pct': momentum_up,
                'bid_volume': bid_volume,
                'ask_volume': ask_volume,
            }
        return {'direction': None, 'reason': 'long_setup_incomplete'}

    pulled_back = last3[0] <= last3[1] >= last3[2]
    reclaim_ok = latest <= swing_high * (1 - RECLAIM_THRESHOLD_PCT)
    if momentum_down >= MOMENTUM_MIN_PCT and pulled_back and reclaim_ok:
        return {
            'direction': 'SHORT',
            'reason': 'micro_pullback_short',
            'momentum_pct': momentum_down,
            'bid_volume': bid_volume,
            'ask_volume': ask_volume,
        }
    return {'direction': None, 'reason': 'short_setup_incomplete'}
