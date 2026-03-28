from momentum_pullback_v2.config import LEVERAGE, RISK_PER_TRADE, FEE_PCT, SLIPPAGE_PCT


def calculate_position_size(balance, entry_price, sl_price):
    risk_amount = balance * RISK_PER_TRADE
    sl_distance = abs(entry_price - sl_price) / max(entry_price, 1e-9)
    if sl_distance <= 0:
        return None
    position_value = risk_amount / sl_distance
    max_position_value = balance * LEVERAGE
    position_value = min(position_value, max_position_value)
    contracts = position_value / max(entry_price, 1e-9)
    if contracts <= 0:
        return None
    return round(contracts, 3)


def build_trade(signal, balance):
    size = calculate_position_size(balance, signal['entry'], signal['sl'])
    if not size:
        return None
    fee = size * signal['entry'] * FEE_PCT * 2
    slip = size * signal['entry'] * SLIPPAGE_PCT * 2
    trade = dict(signal)
    trade.update({'size': size, 'fee': fee, 'slippage': slip, 'max_price': signal['entry'], 'min_price': signal['entry'], 'moved_to_be': False, 'trailing_active': False})
    return trade
