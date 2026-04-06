from reversion_scalp_v1_aggressive.signal import detect_reversion_signal


def scan_all_assets(symbol_to_candles_5m, symbol_to_candles_15m):
    candidates = []
    diagnostics = {}
    for symbol, candles_5m in symbol_to_candles_5m.items():
        signal = detect_reversion_signal(candles_5m, symbol_to_candles_15m.get(symbol, []))
        if not signal or 'rejected' in signal:
            diagnostics[symbol] = signal or {'rejected': 'no_signal_object'}
            continue
        signal['symbol'] = symbol
        candidates.append(signal)
    if not candidates:
        return None, diagnostics
    return sorted(candidates, key=lambda x: x['score'], reverse=True)[0], diagnostics
