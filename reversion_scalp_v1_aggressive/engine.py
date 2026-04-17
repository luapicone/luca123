from datetime import datetime, timezone

from reversion_scalp_v1_aggressive.config import (
    MAX_CONCURRENT_TRADES,
    MAX_CONCURRENT_TRADES_PER_SYMBOL,
    SYMBOL_COOLDOWN_MINUTES,
    SYMBOL_REPEAT_LOSS_COOLDOWN_MINUTES,
)
from reversion_scalp_v1_aggressive.execution import build_trade
from reversion_scalp_v1_aggressive.exit_manager import manage_exit
from reversion_scalp_v1_aggressive.indicators import rsi
from reversion_scalp_v1_aggressive.scanner import scan_all_assets


def select_signals(state, symbol_to_candles_5m, symbol_to_candles_15m, now_ts, max_new_signals=None):
    diagnostics = {}
    selected = []
    if len(state.open_trades) >= MAX_CONCURRENT_TRADES or not symbol_to_candles_5m:
        return selected, diagnostics

    candidates = []
    for symbol, candles_5m in symbol_to_candles_5m.items():
        signal, symbol_diagnostics = scan_all_assets({symbol: candles_5m}, {symbol: symbol_to_candles_15m[symbol]})
        if signal:
            candidates.append(signal)
        elif symbol_diagnostics:
            diagnostics[symbol] = symbol_diagnostics.get(symbol, {'rejected': 'no_signal'})

    candidates = sorted(candidates, key=lambda x: x['score'], reverse=True)
    max_new_signals = max_new_signals if max_new_signals is not None else MAX_CONCURRENT_TRADES

    for signal in candidates:
        if len(selected) >= max_new_signals:
            break
        cooldown_key = f"{signal['symbol']}|{signal['direction']}"
        cooldown_until = state.symbol_cooldowns.get(cooldown_key)
        same_symbol_open = sum(1 for t in state.open_trades if t['symbol'] == signal['symbol'])
        same_symbol_selected = sum(1 for t in selected if t['symbol'] == signal['symbol'])
        if same_symbol_open + same_symbol_selected >= MAX_CONCURRENT_TRADES_PER_SYMBOL:
            diagnostics[signal['symbol']] = {'rejected': 'max_open_trades_per_symbol'}
            continue
        if cooldown_until and now_ts < cooldown_until:
            diagnostics[signal['symbol']] = {'rejected': 'symbol_direction_cooldown'}
            continue
        selected.append(signal)
    return selected, diagnostics


def open_trade_from_signal(signal, balance, opened_at=None):
    trade = build_trade(signal, balance)
    if not trade:
        return None
    trade['opened_at'] = opened_at or datetime.now(timezone.utc)
    return trade


def manage_trade_step(open_trade, candle, minutes_elapsed, rsi_5m):
    current_price = candle[4]
    return manage_exit(open_trade, current_price, candle, minutes_elapsed, rsi_5m)


def close_trade(state, open_trade, exit_price, exit_reason, closed_at):
    gross = (exit_price - open_trade['entry']) * open_trade['size'] if open_trade['direction'] == 'LONG' else (open_trade['entry'] - exit_price) * open_trade['size']
    fee = open_trade['fee'] + open_trade['slippage']
    pnl = gross - fee
    state.balance += pnl
    state.session_peak_balance = max(state.session_peak_balance, state.balance)
    state.trades_today += 1
    state.consecutive_losses = state.consecutive_losses + 1 if pnl <= 0 else 0
    cooldown_key = f"{open_trade['symbol']}|{open_trade['direction']}"
    cooldown_minutes = SYMBOL_REPEAT_LOSS_COOLDOWN_MINUTES if pnl <= 0 else SYMBOL_COOLDOWN_MINUTES
    state.symbol_cooldowns[cooldown_key] = closed_at.timestamp() + (cooldown_minutes * 60)
    return {
        'timestamp': closed_at.isoformat(),
        'symbol': open_trade['symbol'],
        'direction': open_trade['direction'],
        'entry_price': open_trade['entry'],
        'exit_price': exit_price,
        'size': open_trade['size'],
        'pnl': pnl,
        'fee': fee,
        'exit_reason': exit_reason,
        'balance_after': state.balance,
        'score': open_trade.get('score'),
        'stretch': open_trade.get('stretch'),
        'context_rsi': open_trade.get('context_rsi'),
        'zscore': open_trade.get('zscore'),
        'mfe': open_trade.get('mfe'),
        'mae': open_trade.get('mae'),
        'peak_progress': open_trade.get('peak_progress'),
    }


def compute_rsi_from_candles(candles_5m):
    closes = [c[4] for c in candles_5m]
    return rsi(closes, 14) if len(closes) >= 15 else None
