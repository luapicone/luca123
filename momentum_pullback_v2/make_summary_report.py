import sqlite3
from pathlib import Path

LOG_PATH = Path('momentum_pullback_v2/data/bot.log')
DB_PATH = Path('momentum_pullback_v2/data/trades.db')
OUT_PATH = Path('momentum_pullback_v2_summary.txt')


def fetchall(query):
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(query).fetchall()
    finally:
        conn.close()


def main():
    lines = ['===== MOMENTUM PULLBACK V2 SUMMARY =====']

    if DB_PATH.exists():
        summary = fetchall("select count(*), coalesce(sum(pnl),0), coalesce(avg(pnl),0) from trades")
        wins = fetchall("select coalesce(sum(case when pnl > 0 then 1 else 0 end),0), coalesce(sum(case when pnl <= 0 then 1 else 0 end),0), case when count(*) > 0 then round(100.0 * sum(case when pnl > 0 then 1 else 0 end) / count(*), 2) else 0 end from trades")
        trades, total_pnl, avg_pnl = summary[0] if summary else (0, 0, 0)
        win_count, loss_count, wr = wins[0] if wins else (0, 0, 0)
        lines += [
            f'trades: {trades}',
            f'wins: {win_count}',
            f'losses: {loss_count}',
            f'win_rate_pct: {wr}',
            f'total_pnl: {round(total_pnl or 0, 6)}',
            f'avg_pnl: {round(avg_pnl or 0, 6)}',
            ''
        ]
        lines.append('===== LAST 50 TRADES =====')
        rows = fetchall("select id,timestamp,symbol,direction,entry_price,exit_price,size,pnl,fee,exit_reason,balance_after from trades order by id desc limit 50")
        if rows:
            for row in rows:
                lines.append(str(row))
        else:
            lines.append('no trades')
    else:
        lines += ['no trades db', '']

    lines.append('')
    lines.append('===== LAST 200 LOG LINES =====')
    if LOG_PATH.exists():
        log_lines = LOG_PATH.read_text(encoding='utf8', errors='ignore').splitlines()
        lines.extend(log_lines[-200:])
    else:
        lines.append('no log file')

    OUT_PATH.write_text('\n'.join(lines), encoding='utf8')
    print(f'Summary report generated: {OUT_PATH}')


if __name__ == '__main__':
    main()
