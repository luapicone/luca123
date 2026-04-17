"""
reconciliation.py

Al arrancar en modo live, consulta el exchange para detectar:
  1. Posiciones abiertas no rastreadas → phantom_trade con manual_intervention_required.
  2. Para cada phantom_trade: asocia SL/TP reales si existen en open_orders del mismo símbolo.
  3. Órdenes sin posición activa → loguea como warning, NO cancela automáticamente.
  4. Balance real de USDT → inicializa state.balance.
"""

import logging
from datetime import datetime, timezone

from reversion_scalp_v1_aggressive.config import SYMBOLS


# ---------------------------------------------------------------------------
# Parsing de dirección — robusto ante payloads distintos de ccxt/exchange
# ---------------------------------------------------------------------------

def _parse_direction(pos):
    side = (pos.get('side') or '').lower().strip()
    if side in ('long', 'buy'):
        return 'LONG'
    if side in ('short', 'sell'):
        return 'SHORT'
    contracts = pos.get('contracts')
    if contracts is not None:
        try:
            c = float(contracts)
            if c > 0:
                return 'LONG'
            if c < 0:
                return 'SHORT'
        except (TypeError, ValueError):
            pass
    return None


# ---------------------------------------------------------------------------
# Asociar SL/TP reales a un phantom_trade
# ---------------------------------------------------------------------------

def _match_protective_orders(phantom_trade, orders_by_symbol):
    """
    Busca entre las open_orders del mismo símbolo cuáles corresponden
    a un SL (stop_market / stop) y un TP (take_profit_market / take_profit).
    Asigna los IDs encontrados al phantom_trade.

    No asume orden fija — busca por tipo de orden.
    Si encuentra más de uno del mismo tipo, toma el primero y loguea warning.
    """
    symbol    = phantom_trade['symbol']
    direction = phantom_trade['direction']
    orders    = orders_by_symbol.get(symbol, [])

    sl_candidates = []
    tp_candidates = []

    for order in orders:
        order_type = (order.get('type') or '').lower()
        order_side = (order.get('side') or '').lower()

        # Solo nos interesan órdenes reduceOnly o que van en dirección contraria
        is_reduce = order.get('reduceOnly') or order.get('reduce_only') or False
        closes_long  = order_side in ('sell',)
        closes_short = order_side in ('buy',)

        if direction == 'LONG' and not closes_long:
            continue
        if direction == 'SHORT' and not closes_short:
            continue

        if order_type in ('stop_market', 'stop'):
            sl_candidates.append(order)
        elif order_type in ('take_profit_market', 'take_profit'):
            tp_candidates.append(order)

    # Asignar SL
    if sl_candidates:
        if len(sl_candidates) > 1:
            logging.warning(
                '_match_protective_orders: múltiples SL candidatos para %s (%s) — tomando el primero',
                symbol, [o.get('id') for o in sl_candidates]
            )
        sl_order = sl_candidates[0]
        phantom_trade['live_sl_order_id'] = sl_order.get('id')
        phantom_trade['sl'] = float(
            sl_order.get('stopPrice') or sl_order.get('triggerPrice') or sl_order.get('price') or 0
        ) or None
        logging.info(
            '_match_protective_orders: SL asociado id=%s price=%s symbol=%s',
            phantom_trade['live_sl_order_id'], phantom_trade['sl'], symbol
        )
    else:
        logging.warning(
            '_match_protective_orders: no se encontró SL real para phantom_trade %s %s',
            symbol, direction
        )

    # Asignar TP
    if tp_candidates:
        if len(tp_candidates) > 1:
            logging.warning(
                '_match_protective_orders: múltiples TP candidatos para %s (%s) — tomando el primero',
                symbol, [o.get('id') for o in tp_candidates]
            )
        tp_order = tp_candidates[0]
        phantom_trade['live_tp_order_id'] = tp_order.get('id')
        phantom_trade['tp'] = float(
            tp_order.get('stopPrice') or tp_order.get('triggerPrice') or tp_order.get('price') or 0
        ) or None
        logging.info(
            '_match_protective_orders: TP asociado id=%s price=%s symbol=%s',
            phantom_trade['live_tp_order_id'], phantom_trade['tp'], symbol
        )
    else:
        logging.warning(
            '_match_protective_orders: no se encontró TP real para phantom_trade %s %s',
            symbol, direction
        )

    return phantom_trade


# ---------------------------------------------------------------------------
# Punto de entrada principal
# ---------------------------------------------------------------------------

def reconcile_on_boot(exchange, state, settings):
    if not settings.enabled:
        logging.info('reconcile_on_boot: paper mode, skip')
        return

    logging.info('reconcile_on_boot: starting live reconciliation')

    real_balance   = _fetch_real_balance(exchange)
    open_positions = _fetch_open_positions(exchange)
    open_orders    = _fetch_open_orders(exchange)

    # Índice de órdenes por símbolo para búsqueda eficiente
    orders_by_symbol = {}
    for order in open_orders:
        sym = order.get('symbol')
        if sym:
            orders_by_symbol.setdefault(sym, []).append(order)

    # --- 1. Balance real ---
    if real_balance is not None:
        logging.info('reconcile_on_boot: real USDT balance=%.4f (state was %.4f)',
                     real_balance, state.balance)
        state.balance              = real_balance
        state.daily_start_balance  = real_balance
        state.session_peak_balance = real_balance
    else:
        logging.warning('reconcile_on_boot: could not fetch real balance, keeping paper balance')

    # --- 2. Detectar posiciones no rastreadas y asociar sus protecciones ---
    known_symbols  = {t['symbol'] for t in state.open_trades}
    position_symbols = set()

    for pos in open_positions:
        symbol = pos.get('symbol')
        size   = pos.get('contracts') or pos.get('amount') or 0

        if not symbol or float(size) == 0:
            continue

        position_symbols.add(symbol)

        if symbol not in known_symbols:
            direction = _parse_direction(pos)

            if direction is None:
                logging.critical(
                    'reconcile_on_boot: posición real no rastreada %s con dirección INDETERMINADA '
                    'size=%s — no se agrega al state, REVISÁ MANUALMENTE EN EL EXCHANGE',
                    symbol, size
                )
                continue

            entry_price = float(pos.get('entryPrice') or 0)
            phantom_trade = {
                'symbol':                       symbol,
                'direction':                    direction,
                'entry':                        entry_price,
                'size':                         float(size),
                'sl':                           None,
                'tp':                           None,
                'opened_at':                    datetime.now(timezone.utc),
                'manual_intervention_required': True,
                'reconciled_from_exchange':     True,
                'live_sl_order_id':             None,
                'live_tp_order_id':             None,
                'max_price':                    entry_price,
                'min_price':                    entry_price,
                'moved_to_be':                  False,
                'moved_to_be_2':                False,
                'trailing_active':              False,
                'mfe':                          0.0,
                'mae':                          0.0,
                'peak_progress':                0.0,
                'score':                        0.0,
                'stretch':                      0.0,
                'context_rsi':                  None,
                'zscore':                       0.0,
            }

            # Asociar SL/TP reales si existen
            _match_protective_orders(phantom_trade, orders_by_symbol)

            # Si encontramos ambas protecciones, puede manejarse sin intervención manual
            if phantom_trade['live_sl_order_id'] and phantom_trade['live_tp_order_id']:
                phantom_trade['manual_intervention_required'] = False
                logging.warning(
                    'reconcile_on_boot: posición %s %s reconciliada con SL=%s TP=%s — '
                    'manual_intervention_required=False, el bot la retoma',
                    symbol, direction,
                    phantom_trade['live_sl_order_id'],
                    phantom_trade['live_tp_order_id'],
                )
            else:
                logging.critical(
                    'reconcile_on_boot: posición %s %s sin protecciones completas — '
                    'manual_intervention_required=True, REVISÁ MANUALMENTE',
                    symbol, direction
                )

            state.open_trades.append(phantom_trade)

        else:
            logging.info('reconcile_on_boot: posición %s ya rastreada localmente, OK', symbol)

    # --- 3. Reportar órdenes sin posición activa (NO cancelar) ---
    for order in open_orders:
        order_symbol = order.get('symbol')
        if order_symbol not in position_symbols:
            logging.warning(
                'reconcile_on_boot: open order sin posición activa — '
                'id=%s symbol=%s type=%s side=%s — '
                'revisá si es huérfana y cancelá manualmente si corresponde',
                order.get('id'), order_symbol,
                order.get('type', ''), order.get('side', '')
            )

    logging.info('reconcile_on_boot: done | open_trades_after=%s balance=%.4f',
                 len(state.open_trades), state.balance)


# ---------------------------------------------------------------------------
# Helpers de fetch
# ---------------------------------------------------------------------------

def _fetch_real_balance(exchange):
    try:
        balance   = exchange.fetch_balance()
        usdt_free = (balance.get('USDT') or {}).get('free')
        if usdt_free is not None:
            return float(usdt_free)
        total = (balance.get('total') or {}).get('USDT')
        return float(total) if total is not None else None
    except Exception as exc:
        logging.error('_fetch_real_balance failed: %s', exc)
        return None


def _fetch_open_positions(exchange):
    try:
        positions = exchange.fetch_positions(SYMBOLS)
        return [
            p for p in positions
            if float(p.get('contracts') or p.get('amount') or 0) != 0
        ]
    except Exception as exc:
        logging.error('_fetch_open_positions failed: %s', exc)
        return []


def _fetch_open_orders(exchange):
    all_orders = []
    for symbol in SYMBOLS:
        try:
            orders = exchange.fetch_open_orders(symbol)
            all_orders.extend(orders)
        except Exception as exc:
            logging.warning('_fetch_open_orders failed for %s: %s', symbol, exc)
    return all_orders