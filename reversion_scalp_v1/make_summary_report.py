import sqlite3
from pathlib import Path

LOG_PATH = Path('reversion_scalp_v1/data/bot.log')
DB_PATH = Path('reversion_scalp_v1/data/trades.db')
OUT_PATH = Path('reversion_scalp_v1_summary.txt')


def fetchall(query):
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(query).fetchall()
    finally:
        conn.close()


def main():
    lines = ['===== REVERSION SCALP V1 SUMMARY =====']
    if DB_PATH.exists():
        summary = fetchall("select count(*), coalesce(sum(pnl),0), coalesce(avg(pnl),0), coalesce(avg(hold_minutes),0), coalesce(avg(mfe),0), coalesce(avg(mae),0), coalesce(avg(peak_progress),0) from trades")
        wins = fetchall("select coalesce(sum(case when pnl > 0 then 1 else 0 end),0), coalesce(sum(case when pnl <= 0 then 1 else 0 end),0), case when count(*) > 0 then round(100.0 * sum(case when pnl > 0 then 1 else 0 end) / count(*), 2) else 0 end from trades")
        trades, total_pnl, avg_pnl, avg_hold_minutes, avg_mfe, avg_mae, avg_peak_progress = summary[0] if summary else (0, 0, 0, 0, 0, 0, 0)
        win_count, loss_count, wr = wins[0] if wins else (0, 0, 0)
        lines += [
            f'trades: {trades}', f'wins: {win_count}', f'losses: {loss_count}', f'win_rate_pct: {wr}',
            f'total_pnl: {round(total_pnl or 0, 6)}', f'avg_pnl: {round(avg_pnl or 0, 6)}',
            f'avg_hold_minutes: {round(avg_hold_minutes or 0, 4)}', f'avg_mfe: {round(avg_mfe or 0, 6)}',
            f'avg_mae: {round(avg_mae or 0, 6)}', f'avg_peak_progress: {round(avg_peak_progress or 0, 6)}', ''
        ]
        lines.append('===== LAST 50 TRADES =====')
        rows = fetchall("select id,timestamp,symbol,direction,entry_price,exit_price,size,pnl,fee,exit_reason,balance_after,score,stretch,context_rsi,zscore,hold_minutes,mfe,mae,peak_progress from trades order by id desc limit 50")
        if rows:
            lines.extend(str(row) for row in rows)
        else:
            lines.append('no trades')

        lines.append('')
        lines.append('===== PNL BY SYMBOL =====')
        symbol_rows = fetchall("select symbol, count(*), round(sum(pnl), 6), round(avg(pnl), 6), round(100.0 * sum(case when pnl > 0 then 1 else 0 end) / count(*), 2) from trades group by symbol order by sum(pnl) desc")
        if symbol_rows:
            lines.extend(str(row) for row in symbol_rows)
        else:
            lines.append('no symbol stats')

        lines.append('')
        lines.append('===== EXIT REASONS =====')
        exit_rows = fetchall("select exit_reason, count(*), round(sum(pnl), 6) from trades group by exit_reason order by count(*) desc")
        if exit_rows:
            lines.extend(str(row) for row in exit_rows)
        else:
            lines.append('no exit stats')
    else:
        lines += ['no trades db', '']
    lines.append('')
    lines.append('===== LAST 200 LOG LINES =====')
    if LOG_PATH.exists():
        lines.extend(LOG_PATH.read_text(encoding='utf8', errors='ignore').splitlines()[-200:])
    else:
        lines.append('no log file')
    OUT_PATH.write_text('\n'.join(lines), encoding='utf8')
    print(f'Summary report generated: {OUT_PATH}')


if __name__ == '__main__':
    main()
