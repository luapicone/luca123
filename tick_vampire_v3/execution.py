from tick_vampire_v3.config import RISK_PER_TRADE, STOP_PCT, TARGET_PCT, FEE_PCT, CONSECUTIVE_LOSS_SIZE_TRIGGER

def calculate_position_size(balance, eth_price):
    risk_amount = balance * RISK_PER_TRADE
    position_value = risk_amount / STOP_PCT
    contracts = position_value / eth_price
    return round(contracts, 3)

def execute_trade(direction, balance, eth_price, reduced=False):
    size = calculate_position_size(balance, eth_price)
    if reduced:
        size *= 0.5
    if direction == 'LONG':
        entry = eth_price
        tp = entry * (1 + TARGET_PCT)
        sl = entry * (1 - STOP_PCT)
    else:
        entry = eth_price
        tp = entry * (1 - TARGET_PCT)
        sl = entry * (1 + STOP_PCT)
    fee = size * eth_price * FEE_PCT * 2
    return {'direction': direction, 'entry': entry, 'tp': tp, 'sl': sl, 'size': round(size, 3), 'fee': fee}
