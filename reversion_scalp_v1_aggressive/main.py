import logging
import time
from datetime import datetime, timezone

import ccxt
from reversion_scalp_v1_aggressive.live_config import load_live_settings, validate_live_settings
from reversion_scalp_v1_aggressive.discord_bot import notify_open, notify_close, notify_risk_blocked
from reversion_scalp_v1_aggressive.config import EXCHANGE_ID, INITIAL_BALANCE, LOG_PATH, SYMBOLS, TF_CONTEXT, TF_ENTRY, SYMBOL_COOLDOWN_MINUTES, SYMBOL_REPEAT_LOSS_COOLDOWN_MINUTES, MAX_CONCURRENT_TRADES, MAX_CONCURRENT_TRADES_PER_SYMBOL
from reversion_scalp_v1_aggressive.db import init_db, insert_trade
from reversion_scalp_v1_aggressive.engine import close_trade, compute_rsi_from_candles, manage_trade_step, open_trade_from_signal, select_signals
from reversion_scalp_v1_aggressive.live_execution import emergency_close, live_open_trade, place_protective_orders, live_close_trade
from reversion_scalp_v1_aggressive.reconciliation import reconcile_on_boot
from reversion_scalp_v1_aggressive.operational_guard import OperationalGuard
from reversion_scalp_v1_aggressive.risk import risk_checks
from reversion_scalp_v1_aggressive.state import BotState

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()])

settings = load_live_settings()
ok, reason = validate_live_settings(settings)

if not ok:
    raise RuntimeError(f"live config invalid: {reason}")

if settings.enabled:
    logging.warning("=" * 60)
    logging.warning("LIVE MODE ACTIVE")
    logging.warning("=" * 60)
else:
    logging.info("PAPER MODE")


def create_exchange(settings):
    params = {'enableRateLimit': True}

    if settings.enabled:
        params['apiKey'] = settings.api_key
        params['secret'] = settings.api_secret
    params['options'] = {'defaultType': 'future'}

    return getattr(ccxt, EXCHANGE_ID)(params)


def validate_live_exchange_access(exchange, settings):
    if not settings.enabled:
        return
    balance = exchange.fetch_balance()
    usdt_balance = balance.get('USDT', {})
    logging.info('LIVE balance check OK | usdt=%s', usdt_balance)


def validate_live_symbols(exchange, settings):
    if not settings.enabled:
        return

    markets = exchange.load_markets()
    incompatible = []

    for symbol in SYMBOLS:
        market = markets.get(symbol)
        if not market:
            incompatible.append((symbol, 'missing_market'))
            continue

        min_cost = ((market.get('limits') or {}).get('cost') or {}).get('min')
        if min_cost is not None and min_cost > settings.max_live_symbol_notional:
            incompatible.append((symbol, f'min_cost>{settings.max_live_symbol_notional}'))

    if incompatible:
        raise RuntimeError(f'live symbol validation failed: {incompatible}')

    logging.info('LIVE symbol validation OK | symbols=%s', len(SYMBOLS))


def validate_live_trade_size(exchange, trade, settings):
    if not settings.enabled:
        return True, None

    markets = exchange.load_markets()
    market = markets.get(trade['symbol'])
    if not market:
        return False, 'missing_market'

    min_amount = ((market.get('limits') or {}).get('amount') or {}).get('min')
    amount_precision = (market.get('precision') or {}).get('amount')

    size = trade['size']

    if min_amount is not None and size < min_amount:
        return False, f'size_below_min_amount:{size}<{min_amount}'

    if amount_precision is not None:
        rounded = round(size, int(amount_precision)) if isinstance(amount_precision, int) else size
        if rounded <= 0:
            return False, 'rounded_size_invalid'

    return True, None


def fetch_ohlcv_safe(exchange, symbol, timeframe, limit=120, retries=5):
    delay = 1
    for attempt in range(retries):
        try:
            return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        except Exception as exc:
            if attempt == retries - 1:
                raise
            logging.warning('fetch_ohlcv retry %s %s %s: %s', symbol, timeframe, attempt + 1, exc)
            time.sleep(delay)
            delay *= 2


def main():
    init_db()
    exchange = create_exchange(settings)
    validate_live_exchange_access(exchange, settings)
    validate_live_symbols(exchange, settings)
    state = BotState(balance=INITIAL_BALANCE, daily_start_balance=INITIAL_BALANCE, session_peak_balance=INITIAL_BALANCE)
    reconcile_on_boot(exchange, state, settings)
    guard = OperationalGuard(notify_fn=None)  # reemplazar notify_fn con tu función de Discord si querés alertas críticas
    logging.info('Reversion Scalp v1 started | live=%s | exchange=%s', settings.enabled, EXCHANGE_ID)
    cycle = 0

    while True:
        cycle += 1
        logging.info('scan_cycle_start cycle=%s balance=%.6f open_trades=%s', cycle, state.balance, len(state.open_trades))
        if not guard.check_ok():
            continue
        cycle_had_errors = False
        ok, reason = risk_checks(state)
        if not ok:
            logging.warning('risk blocked: %s', reason)
            notify_risk_blocked(reason)
            time.sleep(15)
            continue

        symbol_to_candles_5m = {}
        symbol_to_candles_15m = {}
        for symbol in SYMBOLS:
            try:
                logging.info('fetch_start cycle=%s symbol=%s tf=%s/%s', cycle, symbol, TF_ENTRY, TF_CONTEXT)
                symbol_to_candles_5m[symbol] = fetch_ohlcv_safe(exchange, symbol, TF_ENTRY, limit=120)
                symbol_to_candles_15m[symbol] = fetch_ohlcv_safe(exchange, symbol, TF_CONTEXT, limit=120)
                logging.info('fetch_done cycle=%s symbol=%s candles_5m=%s candles_15m=%s', cycle, symbol, len(symbol_to_candles_5m[symbol]), len(symbol_to_candles_15m[symbol]))
            except Exception as exc:
                logging.warning('fetch failed %s: %s', symbol, exc)
                guard.record_error('fetch_ohlcv', symbol, exc)
                cycle_had_errors = True

        if len(state.open_trades) < MAX_CONCURRENT_TRADES:
            selected_signals, diagnostics = select_signals(
                state,
                symbol_to_candles_5m,
                symbol_to_candles_15m,
                datetime.now(timezone.utc).timestamp(),
                max_new_signals=max(0, MAX_CONCURRENT_TRADES - len(state.open_trades)),
            )
            if selected_signals:
                for signal in selected_signals:
                    if settings.enabled:
                        # --- LIVE: abrir posición real ---
                        trade = live_open_trade(exchange, signal, settings)
                        if trade:
                            try:
                                place_protective_orders(exchange, trade, settings)
                            except RuntimeError as exc:
                                logging.error('protective orders failed after real entry: %s', exc)
                                guard.record_error('place_protective_orders', trade['symbol'], exc)
                                cycle_had_errors = True
                                emergency_ok = emergency_close(exchange, trade)
                                if emergency_ok:
                                    # Posición cerrada limpiamente, descartar
                                    trade = None
                                else:
                                    # Cierre de emergencia también falló:
                                    # conservar en state con flag para no perder el rastro
                                    trade['manual_intervention_required'] = True
                                    trade['opened_at'] = datetime.now(timezone.utc)
                                    state.open_trades.append(trade)
                                    logging.critical(
                                        'EMERGENCY CLOSE FAILED %s — trade conservado localmente con manual_intervention_required, INTERVENCIÓN MANUAL REQUERIDA',
                                        trade['symbol']
                                    )
                                    trade = None  # evitar doble append abajo
                    else:
                        # --- PAPER: simular sin tocar exchange ---
                        trade = open_trade_from_signal(signal, state.balance)
                        if trade:
                            size_ok, size_reason = validate_live_trade_size(exchange, trade, settings)
                            if not size_ok:
                                logging.warning('skip trade %s %s: %s', trade['symbol'], trade['direction'], size_reason)
                                trade = None

                    if trade:
                        trade['opened_at'] = datetime.now(timezone.utc)
                        state.open_trades.append(trade)
                        logging.info('OPEN %s %s entry=%s sl=%s tp=%s size=%s score=%.3f stretch=%.6f zscore=%.3f',
                                     trade['symbol'], trade['direction'], trade['entry'], trade['sl'],
                                     trade['tp'], trade['size'], trade['score'], trade['stretch'], trade['zscore'])
                        notify_open(trade)
            else:
                logging.info('scan_cycle_no_signal cycle=%s symbols_ready=%s diagnostics=%s', cycle, len(symbol_to_candles_5m), diagnostics)

        remaining_open_trades = []
        for open_trade in state.open_trades:
            # Si requiere intervención manual: mantener en lista, loguear y no tocar
            if open_trade.get('manual_intervention_required'):
                logging.critical(
                    'MANUAL INTERVENTION REQUIRED: trade %s %s está en state pero no fue cerrado en exchange — revisá manualmente',
                    open_trade['symbol'], open_trade['direction']
                )
                remaining_open_trades.append(open_trade)
                continue

            candles = symbol_to_candles_5m.get(open_trade['symbol'])
            if not candles:
                remaining_open_trades.append(open_trade)
                continue
            candle = candles[-1]
            current_price = candle[4]
            minutes_elapsed = (datetime.now(timezone.utc) - open_trade['opened_at']).total_seconds() / 60.0
            rsi_5m = compute_rsi_from_candles(candles)
            exit_price, exit_reason, closed = manage_trade_step(open_trade, candle, minutes_elapsed, rsi_5m)
            logging.info('MANAGE %s %s price=%s sl=%s tp=%s reason=%s minutes=%.2f',
                         open_trade['symbol'], open_trade['direction'], current_price,
                         open_trade['sl'], open_trade['tp'], exit_reason, minutes_elapsed)
            if closed:
                if settings.enabled:
                    # --- LIVE: cerrar posición real ---
                    # Si falla, NO cerrar localmente — dejar el trade en remaining para reintentar
                    try:
                        real_fill = live_close_trade(exchange, open_trade, exit_reason)
                        exit_price = real_fill
                    except RuntimeError as exc:
                        logging.error('live_close_trade failed, keeping trade open locally: %s', exc)
                        guard.record_error('live_close_trade', open_trade['symbol'], exc)
                        cycle_had_errors = True
                        remaining_open_trades.append(open_trade)
                        continue

                closed_at = datetime.now(timezone.utc)
                trade_row = close_trade(state, open_trade, exit_price, exit_reason, closed_at)
                trade_row['hold_minutes'] = minutes_elapsed
                insert_trade((trade_row['timestamp'], trade_row['symbol'], trade_row['direction'], trade_row['entry_price'], trade_row['exit_price'], trade_row['size'], trade_row['pnl'], trade_row['fee'], trade_row['exit_reason'], trade_row['balance_after'], trade_row.get('score'), trade_row.get('stretch'), trade_row.get('context_rsi'), trade_row.get('zscore'), trade_row['hold_minutes'], trade_row.get('mfe'), trade_row.get('mae'), trade_row.get('peak_progress')))
                logging.info('CLOSE %s %s pnl=%s fee=%s reason=%s balance=%s mfe=%.6f mae=%.6f peak_progress=%.3f',
                             open_trade['symbol'], open_trade['direction'], round(trade_row['pnl'], 6),
                             round(trade_row['fee'], 6), exit_reason, round(state.balance, 6),
                             open_trade.get('mfe', 0.0), open_trade.get('mae', 0.0), open_trade.get('peak_progress', 0.0))
                notify_close(open_trade, trade_row['pnl'], exit_reason, state.balance)
            else:
                remaining_open_trades.append(open_trade)

        state.open_trades = remaining_open_trades
        guard.record_cycle_end(cycle_had_errors)
        logging.info('scan_cycle_end cycle=%s balance=%.6f open_trades=%s', cycle, state.balance, len(state.open_trades))
        time.sleep(20)


if __name__ == '__main__':
    main()