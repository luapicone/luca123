"""
test_full_flow.py

Simula el ciclo completo del bot en paper mode:
  - Abre un trade con señal sintética
  - Corre el loop de manage con velas que tocan SL o TP
  - Verifica que el trade se cierra con la razón correcta y que el balance se actualiza

No requiere exchange real ni API keys.
Correr con: python -m reversion_scalp_v1_aggressive.test_full_flow
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from reversion_scalp_v1_aggressive.config import INITIAL_BALANCE, FEE_PCT, SLIPPAGE_PCT
from reversion_scalp_v1_aggressive.db import init_db
from reversion_scalp_v1_aggressive.engine import (
    close_trade, compute_rsi_from_candles, manage_trade_step, open_trade_from_signal,
)
from reversion_scalp_v1_aggressive.state import BotState

PASS = []
FAIL = []


def check(name, condition, detail=''):
    if condition:
        PASS.append(name)
        print(f'  PASS  {name}' + (f' ({detail})' if detail else ''))
    else:
        FAIL.append(name)
        print(f'  FAIL  {name}' + (f' — {detail}' if detail else ''))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_signal(direction='LONG', entry=100.0, sl=98.5, tp=101.5, atr=0.5):
    return {
        'symbol':      'SOL/USDT:USDT',
        'direction':   direction,
        'entry':       entry,
        'sl':          sl,
        'tp':          tp,
        'atr':         atr,
        'score':       0.65,
        'stretch':     0.0005,
        'context_rsi': 45.0,
        'zscore':      0.70,
    }


def _make_candles(close_prices, high_offset=0.05, low_offset=0.05, base_ts=1_700_000_000_000):
    """Genera lista de velas [ts, open, high, low, close, vol] a partir de closes."""
    candles = []
    for i, c in enumerate(close_prices):
        ts = base_ts + i * 5 * 60 * 1000  # velas de 5m
        candles.append([ts, c, c + high_offset, c - low_offset, c, 1000.0])
    return candles


def _candle_hit_sl(entry, sl, direction):
    """Vela que toca el SL."""
    if direction == 'LONG':
        return [0, entry, entry + 0.1, sl - 0.1, sl - 0.1, 1000.0]
    else:
        return [0, entry, sl + 0.1, entry - 0.1, sl + 0.1, 1000.0]


def _candle_hit_tp(entry, tp, direction):
    """Vela que toca el TP."""
    if direction == 'LONG':
        return [0, entry, tp + 0.1, entry - 0.05, tp + 0.1, 1000.0]
    else:
        return [0, entry, entry + 0.05, tp - 0.1, tp - 0.1, 1000.0]


def _candle_neutral(price):
    return [0, price, price + 0.05, price - 0.05, price, 1000.0]


def _open_trade(signal, balance):
    trade = open_trade_from_signal(signal, balance)
    trade['opened_at'] = datetime.now(timezone.utc)
    return trade


def _run_manage(trade, candles, minutes=1.0, rsi=45.0):
    """Corre manage_trade_step con la última vela de la lista."""
    trade['last_processed_candle_ts'] = None  # forzar re-evaluación (igual que el loop real)
    candle = candles[-1]
    return manage_trade_step(trade, candle, minutes, rsi)


# ---------------------------------------------------------------------------
# Escenario 1: SL hit en LONG
# ---------------------------------------------------------------------------
print('\n--- Escenario 1: LONG SL hit ---')

state = BotState(balance=INITIAL_BALANCE, daily_start_balance=INITIAL_BALANCE, session_peak_balance=INITIAL_BALANCE)
signal = _make_signal('LONG', entry=100.0, sl=98.5, tp=101.5)
trade = _open_trade(signal, state.balance)

check('trade abierto correctamente', trade is not None)
check('sl correcto', abs(trade['sl'] - 98.5) < 0.001, f'sl={trade["sl"]}')
check('tp correcto', abs(trade['tp'] - 101.5) < 0.001, f'tp={trade["tp"]}')

candles = _make_candles([100.0, 100.1, 99.8])
candles.append(_candle_hit_sl(100.0, 98.5, 'LONG'))

exit_price, reason, closed = _run_manage(trade, candles, minutes=3.0, rsi=45.0)

check('LONG SL detectado', closed and reason == 'SL', f'reason={reason} closed={closed}')
check('SL exit price correcto', abs(exit_price - 98.5) < 0.01, f'exit_price={exit_price}')

balance_before = state.balance
trade_row = close_trade(state, trade, exit_price, reason, datetime.now(timezone.utc))
pnl = trade_row['pnl']
check('LONG SL genera pérdida', pnl < 0, f'pnl={round(pnl, 4)}')
check('balance actualizado tras SL', state.balance < balance_before, f'balance={round(state.balance, 4)}')


# ---------------------------------------------------------------------------
# Escenario 2: TP hit en LONG
# ---------------------------------------------------------------------------
print('\n--- Escenario 2: LONG TP hit ---')

state2 = BotState(balance=INITIAL_BALANCE, daily_start_balance=INITIAL_BALANCE, session_peak_balance=INITIAL_BALANCE)
signal2 = _make_signal('LONG', entry=100.0, sl=98.5, tp=101.5)
trade2 = _open_trade(signal2, state2.balance)

candles2 = _make_candles([100.0, 100.3, 100.8])
candles2.append(_candle_hit_tp(100.0, 101.5, 'LONG'))

exit_price2, reason2, closed2 = _run_manage(trade2, candles2, minutes=4.0, rsi=45.0)

check('LONG TP detectado', closed2 and reason2 == 'TP', f'reason={reason2} closed={closed2}')
check('TP exit price correcto', abs(exit_price2 - 101.5) < 0.01, f'exit_price={exit_price2}')

trade_row2 = close_trade(state2, trade2, exit_price2, reason2, datetime.now(timezone.utc))
check('LONG TP genera ganancia', trade_row2['pnl'] > 0, f'pnl={round(trade_row2["pnl"], 4)}')


# ---------------------------------------------------------------------------
# Escenario 3: SL hit en SHORT
# ---------------------------------------------------------------------------
print('\n--- Escenario 3: SHORT SL hit ---')

state3 = BotState(balance=INITIAL_BALANCE, daily_start_balance=INITIAL_BALANCE, session_peak_balance=INITIAL_BALANCE)
signal3 = _make_signal('SHORT', entry=100.0, sl=101.5, tp=98.5)
trade3 = _open_trade(signal3, state3.balance)

check('SHORT sl correcto (sl > entry)', trade3['sl'] > trade3['entry'], f'sl={trade3["sl"]}')
check('SHORT tp correcto (tp < entry)', trade3['tp'] < trade3['entry'], f'tp={trade3["tp"]}')

candles3 = _make_candles([100.0, 99.9, 99.7])
candles3.append(_candle_hit_sl(100.0, 101.5, 'SHORT'))

exit_price3, reason3, closed3 = _run_manage(trade3, candles3, minutes=3.0, rsi=55.0)

check('SHORT SL detectado', closed3 and reason3 == 'SL', f'reason={reason3} closed={closed3}')

trade_row3 = close_trade(state3, trade3, exit_price3, reason3, datetime.now(timezone.utc))
check('SHORT SL genera pérdida', trade_row3['pnl'] < 0, f'pnl={round(trade_row3["pnl"], 4)}')


# ---------------------------------------------------------------------------
# Escenario 4: TP hit en SHORT
# ---------------------------------------------------------------------------
print('\n--- Escenario 4: SHORT TP hit ---')

state4 = BotState(balance=INITIAL_BALANCE, daily_start_balance=INITIAL_BALANCE, session_peak_balance=INITIAL_BALANCE)
signal4 = _make_signal('SHORT', entry=100.0, sl=101.5, tp=98.5)
trade4 = _open_trade(signal4, state4.balance)

candles4 = _make_candles([100.0, 99.7, 99.2])
candles4.append(_candle_hit_tp(100.0, 98.5, 'SHORT'))

exit_price4, reason4, closed4 = _run_manage(trade4, candles4, minutes=4.0, rsi=55.0)

check('SHORT TP detectado', closed4 and reason4 == 'TP', f'reason={reason4} closed={closed4}')
trade_row4 = close_trade(state4, trade4, exit_price4, reason4, datetime.now(timezone.utc))
check('SHORT TP genera ganancia', trade_row4['pnl'] > 0, f'pnl={round(trade_row4["pnl"], 4)}')


# ---------------------------------------------------------------------------
# Escenario 5: Trailing stop protege ganancia
# ---------------------------------------------------------------------------
print('\n--- Escenario 5: Trailing stop protege ganancia ---')

state5 = BotState(balance=INITIAL_BALANCE, daily_start_balance=INITIAL_BALANCE, session_peak_balance=INITIAL_BALANCE)
signal5 = _make_signal('LONG', entry=100.0, sl=98.0, tp=102.0, atr=0.5)
trade5 = _open_trade(signal5, state5.balance)

# Subida hasta 101.0 (50% hacia TP) → activa trailing
candle_up = [0, 100.0, 101.0, 100.0, 101.0, 1000.0]
trade5['last_processed_candle_ts'] = None
manage_trade_step(trade5, candle_up, 3.0, 45.0)

sl_after_trailing = trade5['sl']
check('Trailing activado tras 50% progreso', trade5['trailing_active'], f'trailing_active={trade5["trailing_active"]}')
check('SL movido por encima de entry', sl_after_trailing > 100.0, f'sl={round(sl_after_trailing, 4)}')

# Retroceso que toca el trailing SL
candle_retrace = [0, 101.0, 101.0, sl_after_trailing - 0.05, sl_after_trailing - 0.05, 1000.0]
trade5['last_processed_candle_ts'] = None
exit_price5, reason5, closed5 = manage_trade_step(trade5, candle_retrace, 5.0, 42.0)

check('Trailing SL cierra trade', closed5 and reason5 == 'SL', f'reason={reason5}')
trade_row5 = close_trade(state5, trade5, exit_price5, reason5, datetime.now(timezone.utc))
check('Trailing SL cierra con ganancia (protegió profit)', trade_row5['pnl'] > 0,
      f'pnl={round(trade_row5["pnl"], 4)} exit={round(exit_price5, 4)}')


# ---------------------------------------------------------------------------
# Escenario 6: Breakeven move (SL se mueve a entry)
# ---------------------------------------------------------------------------
print('\n--- Escenario 6: Breakeven move ---')

state6 = BotState(balance=INITIAL_BALANCE, daily_start_balance=INITIAL_BALANCE, session_peak_balance=INITIAL_BALANCE)
signal6 = _make_signal('LONG', entry=100.0, sl=98.5, tp=102.0, atr=0.5)
trade6 = _open_trade(signal6, state6.balance)

sl_original = trade6['sl']
# Subida a 100.3 (15% de progreso → activa BE a 12%)
candle_be = [0, 100.0, 100.3, 100.0, 100.3, 1000.0]
trade6['last_processed_candle_ts'] = None
manage_trade_step(trade6, candle_be, 2.0, 45.0)

check('BE flag activado', trade6['moved_to_be'])
check('SL movido por encima del original', trade6['sl'] > sl_original,
      f'sl_original={sl_original} → sl_new={round(trade6["sl"], 4)}')


# ---------------------------------------------------------------------------
# Resumen
# ---------------------------------------------------------------------------
print(f'\nResultados: {len(PASS)} pasaron, {len(FAIL)} fallaron')
if FAIL:
    print(f'FALLARON: {FAIL}')
    raise SystemExit(1)
else:
    print('Todos los escenarios del flujo completo pasaron.')
