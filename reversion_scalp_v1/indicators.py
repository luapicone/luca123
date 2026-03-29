from statistics import mean, pstdev


def sma(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def atr(candles, period):
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        high = candles[i][2]
        low = candles[i][3]
        prev_close = candles[i - 1][4]
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def bollinger_bands(closes, period=20, std_mult=2.0):
    if len(closes) < period:
        return None, None, None
    window = closes[-period:]
    mid = mean(window)
    std = pstdev(window)
    return mid - std * std_mult, mid, mid + std * std_mult


def vwap(candles, period=20):
    if len(candles) < period:
        return None
    window = candles[-period:]
    pv = sum(((c[2] + c[3] + c[4]) / 3) * c[5] for c in window)
    vol = sum(c[5] for c in window)
    return pv / vol if vol else None
