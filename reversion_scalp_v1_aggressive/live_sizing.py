"""
live_sizing.py

Sizing endurecido para ejecución real en Binance Futures.
  - balance real del exchange en el momento del sizing
  - size normalizado con amount_to_precision de ccxt
  - sl/tp normalizados con price_to_precision de ccxt
  - validaciones de min_amount, min_cost, min_notional reales
  - cap notional por símbolo
  - validación de net edge después de fees/slippage
"""

import logging

from reversion_scalp_v1_aggressive.config import (
    FEE_PCT, LEVERAGE, MAX_SYMBOL_NOTIONAL, MIN_NET_EDGE_MULTIPLIER,
    RISK_PER_TRADE, SLIPPAGE_PCT,
)


def compute_live_size(exchange, signal, settings):
    """
    Calcula y valida el tamaño de posición para live.
    Devuelve (size, None, sl_normalized, tp_normalized) si OK,
    o (None, reason, None, None) si falla cualquier check.
    """
    symbol    = signal['symbol']
    entry     = signal['entry']
    sl        = signal['sl']
    tp        = signal['tp']
    direction = signal['direction']

    # --- 1. Balance real desde exchange ---
    balance = _fetch_usdt_balance(exchange)
    if balance is None:
        return None, 'cannot_fetch_balance', None, None
    if balance <= 0:
        return None, f'balance_zero_or_negative:{balance}', None, None

    # --- 2. Cargar mercado ---
    try:
        markets = exchange.load_markets()
    except Exception as exc:
        logging.error('compute_live_size: load_markets failed: %s', exc)
        return None, 'load_markets_failed', None, None

    market = markets.get(symbol)
    if not market:
        return None, f'missing_market:{symbol}', None, None

    # --- 3. Normalizar precios sl/tp al precision del mercado ---
    sl_normalized = _normalize_price(exchange, symbol, market, sl, 'sl')
    tp_normalized = _normalize_price(exchange, symbol, market, tp, 'tp')

    if sl_normalized is None:
        return None, f'sl_price_normalization_failed:{sl}', None, None
    if tp_normalized is None:
        return None, f'tp_price_normalization_failed:{tp}', None, None

    # Verificar que la normalización no invirtió la lógica del trade
    if direction == 'LONG':
        if sl_normalized >= entry:
            return None, f'sl_normalized_above_entry:{sl_normalized}>={entry}', None, None
        if tp_normalized <= entry:
            return None, f'tp_normalized_below_entry:{tp_normalized}<={entry}', None, None
    else:
        if sl_normalized <= entry:
            return None, f'sl_normalized_below_entry:{sl_normalized}<={entry}', None, None
        if tp_normalized >= entry:
            return None, f'tp_normalized_above_entry:{tp_normalized}>={entry}', None, None

    # --- 4. Calcular size crudo ---
    sl_distance = abs(entry - sl_normalized) / max(entry, 1e-9)
    if sl_distance <= 0:
        return None, 'sl_distance_zero', None, None

    risk_amount    = balance * RISK_PER_TRADE
    position_value = risk_amount / sl_distance

    symbol_cap     = MAX_SYMBOL_NOTIONAL.get(symbol, balance * 2.0)
    position_value = min(position_value, symbol_cap)

    raw_size = position_value / max(entry, 1e-9)

    # --- 5. Normalizar size con precision real del mercado ---
    try:
        size = float(exchange.amount_to_precision(symbol, raw_size))
    except Exception as exc:
        logging.warning('amount_to_precision failed %s: %s — usando round fallback', symbol, exc)
        precision = (market.get('precision') or {}).get('amount')
        size = round(raw_size, int(precision)) if isinstance(precision, int) else raw_size

    if size <= 0:
        return None, f'size_zero_after_precision:{raw_size}', None, None

    # --- 6. Validar mínimos del mercado ---
    limits       = market.get('limits') or {}
    min_amount   = (limits.get('amount') or {}).get('min')
    min_cost     = (limits.get('cost') or {}).get('min')
    min_notional = (limits.get('market') or {}).get('min')

    if min_amount is not None and size < float(min_amount):
        return None, f'size_below_min_amount:{size}<{min_amount}', None, None

    notional = size * entry
    for label, threshold in [('min_cost', min_cost), ('min_notional', min_notional)]:
        if threshold is not None and notional < float(threshold):
            return None, f'notional_below_{label}:{notional:.4f}<{threshold}', None, None

    # --- 7. Validar net edge real después de fees ---
    gross_tp   = (tp_normalized - entry) * size if direction == 'LONG' else (entry - tp_normalized) * size
    fee        = size * entry * FEE_PCT * 2
    slip       = size * entry * SLIPPAGE_PCT * 2
    total_cost = fee + slip

    if gross_tp <= total_cost * MIN_NET_EDGE_MULTIPLIER:
        return None, f'insufficient_net_edge:gross={gross_tp:.6f} cost={total_cost:.6f}', None, None

    logging.info(
        'compute_live_size OK symbol=%s direction=%s size=%s notional=%.4f '
        'sl=%s tp=%s balance=%.4f risk_amount=%.4f',
        symbol, direction, size, notional, sl_normalized, tp_normalized, balance, risk_amount
    )
    return size, None, sl_normalized, tp_normalized


def _normalize_price(exchange, symbol, market, price, label):
    """
    Normaliza un precio al tick size del mercado usando price_to_precision.
    Devuelve float normalizado, o None si falla.
    """
    try:
        normalized = float(exchange.price_to_precision(symbol, price))
        if normalized != price:
            logging.info('_normalize_price %s %s: %.8f → %.8f', label, symbol, price, normalized)
        return normalized
    except Exception as exc:
        logging.warning('price_to_precision failed %s %s: %s — usando round fallback', label, symbol, exc)
        try:
            tick = (market.get('precision') or {}).get('price')
            if isinstance(tick, int):
                return round(price, tick)
            if isinstance(tick, float) and tick > 0:
                import math
                decimals = max(0, -int(math.floor(math.log10(tick))))
                return round(price, decimals)
            return price
        except Exception as fallback_exc:
            logging.error('_normalize_price fallback failed %s %s: %s', label, symbol, fallback_exc)
            return None


def _fetch_usdt_balance(exchange):
    try:
        balance   = exchange.fetch_balance()
        usdt_free = (balance.get('USDT') or {}).get('free')
        if usdt_free is not None:
            return float(usdt_free)
        total = (balance.get('total') or {}).get('USDT')
        return float(total) if total is not None else None
    except Exception as exc:
        logging.error('_fetch_usdt_balance failed: %s', exc)
        return None