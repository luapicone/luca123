import logging
import ccxt


def _normalize_size(size, market):
    precision = (market.get('precision') or {}).get('amount')
    if precision is not None and isinstance(precision, int):
        size = round(size, precision)
    return size


def live_open_trade(exchange, signal, settings):
    """
    Abre una orden de mercado real en Binance Futures.
    Usa compute_live_size() para sizing endurecido con balance real del exchange.
    Devuelve trade dict enriquecido con fill real, o None si falla.
    NO coloca protecciones — eso es responsabilidad de place_protective_orders().
    """
    from reversion_scalp_v1_aggressive.live_sizing import compute_live_size
    from reversion_scalp_v1_aggressive.config import LEVERAGE

    symbol    = signal['symbol']
    direction = signal['direction']
    side      = 'buy' if direction == 'LONG' else 'sell'

    # Sizing endurecido: balance real, precision real, validaciones reales
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
        logging.info('live_open_trade order_id=%s symbol=%s side=%s size=%s',
                     order.get('id'), symbol, side, size)

        fill_price = order.get('average') or order.get('price') or signal['entry']
        fill_size  = order.get('filled') or size

        trade = dict(signal)
        trade.update({
            'entry':               fill_price,
            'size':                fill_size,
            'sl':                  sl,
            'tp':                  tp,
            'live_order_id':       order.get('id'),
            'live_sl_order_id':    None,
            'live_tp_order_id':    None,
            'max_price':           fill_price,
            'min_price':           fill_price,
            'moved_to_be':         False,
            'moved_to_be_2':       False,
            'trailing_active':     False,
            'mfe':                 0.0,
            'mae':                 0.0,
            'peak_progress':       0.0,
        })

        logging.info('live_open_trade filled symbol=%s side=%s fill_price=%s fill_size=%s',
                     symbol, side, fill_price, fill_size)
        return trade

    except ccxt.InsufficientFunds as exc:
        logging.error('live_open_trade InsufficientFunds %s: %s', symbol, exc)
        return None
    except ccxt.InvalidOrder as exc:
        logging.error('live_open_trade InvalidOrder %s: %s', symbol, exc)
        return None
    except Exception as exc:
        logging.error('live_open_trade unexpected error %s: %s', symbol, exc)
        return None


def emergency_close(exchange, trade):
    """
    Cierra de emergencia una posición real con market reduceOnly.
    Se llama únicamente cuando place_protective_orders falla después de una entry real.
    Devuelve True si el cierre fue exitoso, False si no.
    """
    symbol = trade['symbol']
    size   = trade['size']
    side   = 'sell' if trade['direction'] == 'LONG' else 'buy'

    logging.warning('EMERGENCY CLOSE initiated symbol=%s side=%s size=%s', symbol, side, size)
    try:
        order = exchange.create_market_order(symbol, side, size, params={'reduceOnly': True})
        logging.warning('EMERGENCY CLOSE filled symbol=%s fill=%s', symbol, order.get('average'))
        return True
    except Exception as exc:
        logging.critical(
            'EMERGENCY CLOSE FAILED symbol=%s: %s — POSICIÓN REAL ABIERTA SIN PROTECCIÓN, INTERVENCIÓN MANUAL REQUERIDA',
            symbol, exc
        )
        return False


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

    # --- Stop Loss ---
    try:
        sl_order = exchange.create_order(
            symbol, 'stop_market', sl_side, size,
            params={'stopPrice': trade['sl'], 'reduceOnly': True}
        )
        sl_order_id = sl_order.get('id')
        logging.info('SL placed order_id=%s symbol=%s price=%s', sl_order_id, symbol, trade['sl'])
    except Exception as exc:
        logging.error('SL FAILED %s: %s', symbol, exc)
        raise RuntimeError(f'SL order failed for {symbol}: {exc}')

    # --- Take Profit ---
    try:
        tp_order = exchange.create_order(
            symbol, 'take_profit_market', tp_side, size,
            params={'stopPrice': trade['tp'], 'reduceOnly': True}
        )
        tp_order_id = tp_order.get('id')
        logging.info('TP placed order_id=%s symbol=%s price=%s', tp_order_id, symbol, trade['tp'])
    except Exception as exc:
        logging.error('TP FAILED %s: %s — cancelando SL %s', symbol, exc, sl_order_id)
        if sl_order_id:
            try:
                exchange.cancel_order(sl_order_id, symbol)
                logging.warning('SL cancelado por fallo de TP order_id=%s', sl_order_id)
            except Exception as cancel_exc:
                logging.error('no se pudo cancelar SL %s: %s', sl_order_id, cancel_exc)
        raise RuntimeError(f'TP order failed for {symbol}: {exc}')

    trade['live_sl_order_id'] = sl_order_id
    trade['live_tp_order_id'] = tp_order_id
    return trade


def live_close_trade(exchange, trade, exit_reason):
    """
    Cancela SL/TP pendientes y cierra con market reduceOnly.
    Devuelve el precio de fill real, o lanza RuntimeError si falla.
    El caller NO debe cerrar localmente si esto lanza — debe dejar el trade abierto.
    """
    symbol = trade['symbol']
    size   = trade['size']
    side   = 'sell' if trade['direction'] == 'LONG' else 'buy'

    # Cancelar órdenes protectoras primero
    for order_key in ('live_sl_order_id', 'live_tp_order_id'):
        order_id = trade.get(order_key)
        if order_id:
            try:
                exchange.cancel_order(order_id, symbol)
                logging.info('cancelled %s order_id=%s', order_key, order_id)
            except Exception as exc:
                # No fatal — puede que ya se haya ejecutado
                logging.warning('cancel %s failed %s: %s', order_key, order_id, exc)

    try:
        order = exchange.create_market_order(symbol, side, size, params={'reduceOnly': True})
        fill_price = order.get('average') or order.get('price')
        if not fill_price:
            raise RuntimeError(f'fill_price missing in close order response for {symbol}')
        logging.info('live_close_trade filled symbol=%s side=%s fill=%s reason=%s',
                     symbol, side, fill_price, exit_reason)
        return fill_price
    except Exception as exc:
        logging.critical(
            'live_close_trade FAILED %s reason=%s: %s — trade permanece abierto localmente',
            symbol, exit_reason, exc
        )
        raise RuntimeError(f'close failed for {symbol}: {exc}')