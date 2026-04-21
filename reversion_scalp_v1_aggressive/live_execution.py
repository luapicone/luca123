import logging
import time
import ccxt


# ---------------------------------------------------------------------------
# Constantes internas
# ---------------------------------------------------------------------------
_FETCH_ORDER_RETRIES  = 3
_FETCH_ORDER_DELAY_S  = 1.0   # espera entre reintentos de confirmación
_FILL_TIMEOUT_S       = 8.0   # tiempo máximo esperando fill completo


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _confirm_fill(exchange, order_id, symbol, expected_size, timeout_s=_FILL_TIMEOUT_S):
    """
    Hace fetch del order real en el exchange para confirmar fill.
    El loop está gobernado por deadline real — itera mientras quede tiempo,
    con _FETCH_ORDER_DELAY_S entre intentos.
    Devuelve (fill_price, fill_size) confirmados, o lanza RuntimeError al agotar tiempo.
    """
    deadline   = time.monotonic() + timeout_s
    last_order = None
    attempt    = 0

    while time.monotonic() < deadline:
        attempt += 1
        try:
            order      = exchange.fetch_order(order_id, symbol)
            last_order = order
            status     = (order.get('status') or '').lower()
            fill_size  = float(order.get('filled') or 0)
            fill_price = float(order.get('average') or order.get('price') or 0)

            if status == 'closed' and fill_size > 0 and fill_price > 0:
                logging.info(
                    '_confirm_fill OK order_id=%s symbol=%s fill_price=%.6f fill_size=%s attempt=%s',
                    order_id, symbol, fill_price, fill_size, attempt
                )
                return fill_price, fill_size

            logging.info(
                '_confirm_fill waiting order_id=%s status=%s filled=%s/%s attempt=%s remaining=%.1fs',
                order_id, status, fill_size, expected_size, attempt,
                max(0.0, deadline - time.monotonic())
            )

        except Exception as exc:
            logging.warning('_confirm_fill fetch failed attempt=%s: %s', attempt, exc)

        # Esperar antes del próximo intento, solo si queda tiempo suficiente
        remaining = deadline - time.monotonic()
        if remaining > _FETCH_ORDER_DELAY_S:
            time.sleep(_FETCH_ORDER_DELAY_S)
        elif remaining > 0:
            time.sleep(remaining)

    # Deadline agotado
    status     = (last_order or {}).get('status', 'unknown')
    fill_size  = float((last_order or {}).get('filled') or 0)
    fill_price = float((last_order or {}).get('average') or (last_order or {}).get('price') or 0)

    raise RuntimeError(
        f'_confirm_fill timeout after {timeout_s}s order_id={order_id} symbol={symbol} '
        f'status={status} filled={fill_size}/{expected_size} price={fill_price}'
    )


def _confirm_position_closed(exchange, symbol, retries=3, delay_s=1.0):
    """
    Verifica en el exchange que no haya posición abierta para el símbolo.
    Útil para confirmar que el cierre fue efectivo.
    Devuelve True si la posición está cerrada (size == 0), False si no.
    """
    for attempt in range(retries):
        try:
            positions = exchange.fetch_positions([symbol])
            position_still_open = False
            for pos in positions:
                size = float(pos.get('contracts') or pos.get('amount') or 0)
                if pos.get('symbol') == symbol and size != 0:
                    position_still_open = True
                    logging.warning(
                        '_confirm_position_closed: posición todavía abierta %s size=%s attempt=%s',
                        symbol, size, attempt + 1
                    )
                    break
            if not position_still_open:
                return True
            if attempt < retries - 1:
                time.sleep(delay_s)
        except Exception as exc:
            logging.warning('_confirm_position_closed fetch failed %s attempt=%s: %s',
                            symbol, attempt + 1, exc)
            if attempt < retries - 1:
                time.sleep(delay_s)
    # Si todos los fetches fallaron, no podemos confirmar — asumimos no cerrado (más seguro)
    return False


def _shift_levels_to_fill(exchange, symbol, direction, signal_entry, sl, tp, fill_price):
    sl_offset = abs(signal_entry - sl)
    tp_offset = abs(signal_entry - tp)

    if direction == 'LONG':
        shifted_sl = fill_price - sl_offset
        shifted_tp = fill_price + tp_offset
    else:
        shifted_sl = fill_price + sl_offset
        shifted_tp = fill_price - tp_offset

    try:
        shifted_sl = float(exchange.price_to_precision(symbol, shifted_sl))
        shifted_tp = float(exchange.price_to_precision(symbol, shifted_tp))
    except Exception as exc:
        logging.warning('_shift_levels_to_fill precision fallback %s: %s', symbol, exc)

    return shifted_sl, shifted_tp


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def live_open_trade(exchange, signal, settings):
    """
    Abre una orden de mercado real en Binance Futures.
    Confirma el fill con fetch_order post-ejecución.
    Devuelve trade dict con fill confirmado, o None si falla.
    NO coloca protecciones — eso es responsabilidad de place_protective_orders().
    """
    from reversion_scalp_v1_aggressive.live_sizing import compute_live_size
    from reversion_scalp_v1_aggressive.config import LEVERAGE

    symbol    = signal['symbol']
    direction = signal['direction']
    side      = 'buy' if direction == 'LONG' else 'sell'

    size, size_error, sl, tp = compute_live_size(exchange, signal, settings)
    if size is None:
        logging.warning('live_open_trade: sizing rejected %s %s: %s', symbol, direction, size_error)
        return None

    try:
        try:
            exchange.set_leverage(LEVERAGE, symbol)
        except Exception as exc:
            logging.warning('set_leverage failed %s: %s', symbol, exc)

        order = exchange.create_market_order(symbol, side, size)
        order_id = order.get('id')
        logging.info('live_open_trade order sent order_id=%s symbol=%s side=%s size=%s',
                     order_id, symbol, side, size)

        if not order_id:
            raise RuntimeError(f'create_market_order returned no order_id for {symbol}')

        # Confirmar fill real desde exchange — no confiar solo en la respuesta inmediata
        fill_price, fill_size = _confirm_fill(exchange, order_id, symbol, expected_size=size)
        live_sl, live_tp = _shift_levels_to_fill(exchange, symbol, direction, signal['entry'], sl, tp, fill_price)

        from reversion_scalp_v1_aggressive.config import FEE_PCT, SLIPPAGE_PCT
        fee  = fill_size * fill_price * FEE_PCT * 2
        slip = fill_size * fill_price * SLIPPAGE_PCT * 2

        trade = dict(signal)
        trade.update({
            'entry':                    fill_price,
            'size':                     fill_size,
            'sl':                       live_sl,
            'tp':                       live_tp,
            'fee':                      fee,
            'slippage':                 slip,
            'live_order_id':            order_id,
            'live_sl_order_id':         None,
            'live_tp_order_id':         None,
            'max_price':                fill_price,
            'min_price':                fill_price,
            'moved_to_be':              False,
            'trailing_active':          False,
            'mfe':                      0.0,
            'mae':                      0.0,
            'peak_progress':            0.0,
            'last_processed_candle_ts': None,
            'last_replayed_minute_ts':  None,
        })

        logging.info('live_open_trade confirmed symbol=%s fill_price=%.6f fill_size=%s live_sl=%s live_tp=%s',
                     symbol, fill_price, fill_size, live_sl, live_tp)
        return trade

    except ccxt.InsufficientFunds as exc:
        logging.error('live_open_trade InsufficientFunds %s: %s', symbol, exc)
        return None
    except ccxt.InvalidOrder as exc:
        logging.error('live_open_trade InvalidOrder %s: %s', symbol, exc)
        return None
    except RuntimeError as exc:
        # _confirm_fill timeout — la orden puede estar parcialmente llena en el exchange.
        # Intentar emergency_close para no dejar exposición real sin rastrear.
        # El caller recibirá None y no agregará el trade localmente — pero la posición
        # puede quedar abierta si emergency_close también falla (se loguea critical).
        logging.error('live_open_trade fill confirmation failed %s: %s — intentando emergency_close', symbol, exc)
        phantom = {'symbol': symbol, 'direction': direction, 'size': size,
                   'live_sl_order_id': None, 'live_tp_order_id': None}
        emergency_closed = emergency_close(exchange, phantom)
        if not emergency_closed:
            logging.critical(
                'live_open_trade: fill no confirmado Y emergency_close falló %s — '
                'posible exposición real sin rastrear, REVISÁ MANUALMENTE',
                symbol
            )
        return None
    except Exception as exc:
        logging.error('live_open_trade unexpected error %s: %s', symbol, exc)
        return None


def emergency_close(exchange, trade):
    """
    Cierra de emergencia una posición real con market reduceOnly.
    Confirma que la posición quedó efectivamente cerrada en el exchange.
    Devuelve True si confirmado cerrado, False si no.
    """
    symbol = trade['symbol']
    size   = trade['size']
    side   = 'sell' if trade['direction'] == 'LONG' else 'buy'

    logging.warning('EMERGENCY CLOSE initiated symbol=%s side=%s size=%s', symbol, side, size)
    try:
        order = exchange.create_market_order(symbol, side, size, params={'reduceOnly': True})
        order_id = order.get('id')
        logging.warning('EMERGENCY CLOSE order sent order_id=%s symbol=%s', order_id, symbol)
    except Exception as exc:
        logging.critical(
            'EMERGENCY CLOSE order FAILED symbol=%s: %s — POSICIÓN REAL ABIERTA SIN PROTECCIÓN',
            symbol, exc
        )
        return False

    # Confirmar que la posición realmente quedó cerrada
    closed = _confirm_position_closed(exchange, symbol)
    if closed:
        logging.warning('EMERGENCY CLOSE confirmed closed symbol=%s', symbol)
    else:
        logging.critical(
            'EMERGENCY CLOSE: orden enviada pero posición todavía abierta en %s — INTERVENCIÓN MANUAL REQUERIDA',
            symbol
        )
    return closed


def place_protective_orders(exchange, trade, settings):
    """
    Coloca SL (stop_market) y TP (take_profit_market) reales.
    Si el TP falla: cancela el SL y lanza RuntimeError.
    El caller es responsable de llamar emergency_close() si esto falla.
    """
    symbol    = trade['symbol']
    size      = trade['size']
    direction = trade['direction']
    sl_side   = 'sell' if direction == 'LONG' else 'buy'
    tp_side   = 'sell' if direction == 'LONG' else 'buy'

    sl_order_id = None

    # ccxt 4.4.99 + binanceusdm: para STOP_MARKET y TAKE_PROFIT_MARKET en Futures
    # hay que usar stopLossPrice / takeProfitPrice en params con type='market'.
    # ccxt deriva el tipo de orden (STOP_MARKET / TAKE_PROFIT_MARKET) de esos params.
    # reduceOnly como string 'true' (no bool) para Futures.
    # Binance Argentina bloquea STOP_MARKET en /fapi/v1/order con -4120.
    # El bot gestiona SL/TP por software: monitorea precio cada ciclo y
    # cierra con MARKET cuando se toca el nivel. No se colocan ordenes
    # protectoras en el exchange.
    sl_order_id = None
    tp_order_id = None
    logging.info('protective_orders skipped: usando SL/TP por software symbol=%s sl=%s tp=%s',
                 symbol, trade['sl'], trade['tp'])

    trade['live_sl_order_id'] = sl_order_id
    trade['live_tp_order_id'] = tp_order_id
    return trade


def live_close_trade(exchange, trade, exit_reason):
    """
    Cancela SL/TP pendientes, cierra con market reduceOnly,
    y confirma fill con fetch_order post-ejecución.
    Lanza RuntimeError si el cierre falla o no se puede confirmar.
    El caller NO debe cerrar localmente si esto lanza.
    """
    symbol = trade['symbol']
    size   = trade['size']
    side   = 'sell' if trade['direction'] == 'LONG' else 'buy'

    for order_key in ('live_sl_order_id', 'live_tp_order_id'):
        order_id = trade.get(order_key)
        if order_id:
            try:
                exchange.cancel_order(order_id, symbol)
                logging.info('cancelled %s order_id=%s', order_key, order_id)
            except Exception as exc:
                logging.warning('cancel %s failed %s: %s', order_key, order_id, exc)

    try:
        order = exchange.create_market_order(symbol, side, size, params={'reduceOnly': True})
        order_id = order.get('id')
        if not order_id:
            raise RuntimeError(f'close order returned no order_id for {symbol}')

        logging.info('live_close_trade order sent order_id=%s symbol=%s side=%s reason=%s',
                     order_id, symbol, side, exit_reason)

        # Confirmar fill real
        fill_price, fill_size = _confirm_fill(exchange, order_id, symbol, expected_size=size)
        if abs(fill_size - size) > max(1e-9, size * 0.01):
            raise RuntimeError(
                f'close fill_size mismatch for {symbol}: filled={fill_size} expected={size}'
            )

        # Verificar que la posición quedó efectivamente cerrada
        position_closed = _confirm_position_closed(exchange, symbol, retries=5, delay_s=1.0)
        if not position_closed:
            raise RuntimeError(
                f'close not fully confirmed for {symbol}: position still visible after market close'
            )

        logging.info('live_close_trade confirmed symbol=%s fill=%.6f reason=%s',
                     symbol, fill_price, exit_reason)
        return fill_price

    except RuntimeError:
        raise
    except Exception as exc:
        logging.critical(
            'live_close_trade FAILED %s reason=%s: %s — trade permanece abierto localmente',
            symbol, exit_reason, exc
        )
        raise RuntimeError(f'close failed for {symbol}: {exc}')
