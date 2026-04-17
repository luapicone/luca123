import argparse
from datetime import datetime, timedelta, timezone

import ccxt

from reversion_scalp_v1_aggressive.backtest import (
    TIMEFRAME_MS,
    aggregate_candles,
    build_snapshot_from_1m,
    create_exchange,
    fetch_all_ohlcv,
    next_1m_bar_after,
)
from reversion_scalp_v1_aggressive.engine import compute_rsi_from_candles, manage_trade_step, open_trade_from_signal, select_signals
from reversion_scalp_v1_aggressive.state import BotState
from reversion_scalp_v1_aggressive.config import INITIAL_BALANCE


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=3)
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--trade-index', type=int, default=0)
    args = parser.parse_args()

    exchange = create_exchange()
    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    since_ms = int(since.timestamp() * 1000)
    until_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    data_1m = {args.symbol: fetch_all_ohlcv(exchange, args.symbol, '1m', since_ms, until_ms)}
    first_ts = data_1m[args.symbol][0][0]
    last_ts = data_1m[args.symbol][-1][0]
    required_warmup_ms = max(120 * TIMEFRAME_MS['5m'], 20 * TIMEFRAME_MS['15m'])
    scan_ts = first_ts + required_warmup_ms

    state = BotState(balance=INITIAL_BALANCE, daily_start_balance=INITIAL_BALANCE, session_peak_balance=INITIAL_BALANCE)
    pending_trades = []
    seen_trades = 0

    while scan_ts <= last_ts:
        timestamp = datetime.fromtimestamp(scan_ts / 1000, tz=timezone.utc)
        still_pending = []
        for pending in pending_trades:
            if pending['activate_at'] <= scan_ts:
                pending['trade']['opened_at'] = timestamp
                state.open_trades.append(pending['trade'])
            else:
                still_pending.append(pending)
        pending_trades = still_pending

        s5, s15, _ = build_snapshot_from_1m(data_1m, [args.symbol], scan_ts)
        selected, _ = select_signals(state, s5, s15, timestamp.timestamp(), max_new_signals=1)
        for signal in selected:
            trade = open_trade_from_signal(signal, state.balance, opened_at=timestamp)
            next_bar = next_1m_bar_after(data_1m[args.symbol], scan_ts)
            if trade and next_bar:
                trade.pop('opened_at', None)
                pending_trades.append({'trade': trade, 'activate_at': next_bar[0]})

        remaining = []
        for open_trade in state.open_trades:
            last_replayed_minute_ts = open_trade.get('last_replayed_minute_ts')
            lower_bound = last_replayed_minute_ts if last_replayed_minute_ts is not None else int(open_trade['opened_at'].timestamp() * 1000)
            symbol_rows = [r for r in data_1m[args.symbol] if lower_bound < r[0] <= scan_ts]
            base_1m_rows = [r for r in data_1m[args.symbol] if r[0] <= scan_ts]
            candles_5m = aggregate_candles(base_1m_rows, TIMEFRAME_MS['5m'], scan_ts)
            rsi_5m = compute_rsi_from_candles(candles_5m[-120:])
            closed = False
            for candle_1m in symbol_rows:
                open_trade['last_replayed_minute_ts'] = candle_1m[0]
                minutes_elapsed = (datetime.fromtimestamp((candle_1m[0] + TIMEFRAME_MS['1m']) / 1000, tz=timezone.utc) - open_trade['opened_at']).total_seconds() / 60.0
                exit_price, exit_reason, closed = manage_trade_step(open_trade, candle_1m, minutes_elapsed, rsi_5m)
                if seen_trades == args.trade_index:
                    print({
                        'trade_index': seen_trades,
                        'scan_ts': timestamp.isoformat(),
                        'minute_ts': datetime.fromtimestamp(candle_1m[0] / 1000, tz=timezone.utc).isoformat(),
                        'entry': open_trade['entry'],
                        'sl': open_trade['sl'],
                        'tp': open_trade['tp'],
                        'close_1m': candle_1m[4],
                        'high_1m': candle_1m[2],
                        'low_1m': candle_1m[3],
                        'exit_price': exit_price,
                        'exit_reason': exit_reason,
                        'closed': closed,
                        'minutes_elapsed': minutes_elapsed,
                        'mfe': open_trade.get('mfe'),
                        'mae': open_trade.get('mae'),
                        'peak_progress': open_trade.get('peak_progress'),
                    })
                if closed:
                    break
            if closed:
                if seen_trades == args.trade_index:
                    return
                seen_trades += 1
            else:
                remaining.append(open_trade)
        state.open_trades = remaining
        scan_ts += 20 * 1000


if __name__ == '__main__':
    main()
