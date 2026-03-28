from momentum_pullback_v2.config import SCORE_MIN_THRESHOLD
from momentum_pullback_v2.momentum import detect_momentum_pullback


def scan_all_assets(symbol_to_candles_5m, symbol_to_candles_15m):
    candidates = []
    for symbol, candles_5m in symbol_to_candles_5m.items():
        candles_15m = symbol_to_candles_15m.get(symbol, [])
        signal = detect_momentum_pullback(candles_5m, candles_15m)
        if not signal:
            continue
        if signal['score'] < SCORE_MIN_THRESHOLD:
            continue
        signal['symbol'] = symbol
        candidates.append(signal)
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x['score'], reverse=True)[0]
