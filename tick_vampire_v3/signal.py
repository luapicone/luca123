from collections import deque
from statistics import mean
from tick_vampire_v3.config import (
    ORDER_BOOK_LEVELS, DELTA_IMBALANCE_MIN, RSI_MIN, RSI_MAX, SPREAD_MAX_PCT,
    ROUND_NUMBER_BUFFER, FUNDING_RATE_MAX
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


def check_entry_signal(orderbook, rsi, volume, volume_ma, spread, eth_price, funding_rate):
    bids = orderbook.get('bids', [])[:ORDER_BOOK_LEVELS]
    asks = orderbook.get('asks', [])[:ORDER_BOOK_LEVELS]
    bid_volume = sum(size for _, size in bids)
    ask_volume = sum(size for _, size in asks)
    if bid_volume <= 0 or ask_volume <= 0:
        return None
    long_signal = (bid_volume / ask_volume) >= DELTA_IMBALANCE_MIN
    short_signal = (ask_volume / bid_volume) >= DELTA_IMBALANCE_MIN
    rsi_ok = RSI_MIN <= rsi <= RSI_MAX
    spread_ok = spread <= SPREAD_MAX_PCT * eth_price
    volume_ok = volume > volume_ma
    round_numbers = [1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000]
    round_number_ok = all(abs(eth_price - rn) / rn > ROUND_NUMBER_BUFFER for rn in round_numbers)
    funding_ok = abs(funding_rate) <= FUNDING_RATE_MAX
    if all([rsi_ok, spread_ok, volume_ok, round_number_ok, funding_ok]):
        if long_signal:
            return 'LONG'
        if short_signal:
            return 'SHORT'
    return None
