from reversion_scalp_v1_aggressive.discord_bot import notify_open, notify_close

trade_falso = {
    'symbol': 'SOL/USDT:USDT',
    'direction': 'LONG',
    'entry': 83.44,
    'sl': 83.14,
    'tp': 83.74,
    'size': 2.387,
    'score': 0.623,
    'stretch': 0.00021,
    'zscore': 0.71,
}

notify_open(trade_falso)
notify_close(trade_falso, pnl=0.064, exit_reason='TP', balance=101.56)

print("Mensajes enviados — revisá Discord")