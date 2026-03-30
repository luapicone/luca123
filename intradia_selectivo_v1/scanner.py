from intradia_selectivo_v1.signal import detect_intraday_signal


def scan_all_assets(symbol_to_candles_15m, symbol_to_candles_1h):
    candidates = []
    diagnostics = {}
    for symbol, candles_15m in symbol_to_candles_15m.items():
        signal = detect_intraday_signal(candles_15m, symbol_to_candles_1h.get(symbol, []))
        if not signal or 'rejected' in signal:
            diagnostics[symbol] = signal or {'rejected': 'no_signal_object'}
            continue
        signal['symbol'] = symbol
        candidates.append(signal)
    if not candidates:
        return None, diagnostics
    return sorted(candidates, key=lambda x: x['score'], reverse=True)[0], diagnostics
