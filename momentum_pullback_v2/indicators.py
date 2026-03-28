import numpy as np


def rsi(closes, period=14):
    closes = np.asarray(closes, dtype=float)
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains = np.clip(deltas, 0, None)
    losses = np.clip(-deltas, 0, None)
    avg_gain = gains[-period:].mean() if gains[-period:].size else 0.0
    avg_loss = losses[-period:].mean() if losses[-period:].size else 1e-9
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(ohlcv, period=14):
    if len(ohlcv) < period + 1:
        return None
    highs = np.array([c[2] for c in ohlcv], dtype=float)
    lows = np.array([c[3] for c in ohlcv], dtype=float)
    closes = np.array([c[4] for c in ohlcv], dtype=float)
    prev_closes = np.roll(closes, 1)
    prev_closes[0] = closes[0]
    tr = np.maximum(highs - lows, np.maximum(np.abs(highs - prev_closes), np.abs(lows - prev_closes)))
    return float(np.mean(tr[-period:]))


def sma(values, period):
    arr = np.asarray(values, dtype=float)
    if len(arr) < period:
        return None
    return float(arr[-period:].mean())
