import sqlite3
from pathlib import Path

DB_PATH = Path('tick_vampire_v3/trades.db')
LOG_PATH = Path('tick_vampire_v3/tick_vampire.log')
OUT_PATH = Path('tick_vampire_v3_report.txt')


def fetch_rows(query):
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(query).fetchall()
    conn.close()
    return rows


def main():
    lines = []
    lines.append('===== TICK VAMPIRE v3 REPORT =====')

    summary = fetch_rows('''
        select
            count(*) as trades,
            sum(case when pnl >= 0 then 1 else 0 end) as wins,
            sum(case when pnl < 0 then 1 else 0 end) as losses,
            coalesce(sum(pnl), 0),
            coalesce(avg(pnl), 0),
            coalesce(max(pnl), 0),
            coalesce(min(pnl), 0)
        from trades
    ''')
    if summary:
        trades, wins, losses, total_pnl, avg_pnl, best, worst = summary[0]
        wr = (wins / trades * 100) if trades else 0.0
        lines += [
            f'trades: {trades}',
            f'wins: {wins}',
            f'losses: {losses}',
            f'win_rate_pct: {round(wr, 4)}',
            f'total_pnl: {round(total_pnl or 0, 6)}',
            f'avg_pnl: {round(avg_pnl or 0, 6)}',
            f'best_trade: {round(best or 0, 6)}',
            f'worst_trade: {round(worst or 0, 6)}',
        ]
    else:
        lines.append('no trades db found')

    lines.append('')
    lines.append('===== LAST 20 TRADES =====')
    rows = fetch_rows('''
        select id,timestamp,direction,entry_price,exit_price,size,pnl,fee,exit_reason,session,balance_after
        from trades order by id desc limit 20
    ''')
    if rows:
        for row in rows:
            lines.append(str(row))
    else:
        lines.append('no trades')

    lines.append('')
    lines.append('===== LAST 100 LOG LINES =====')
    if LOG_PATH.exists():
        log_lines = LOG_PATH.read_text().splitlines()
        lines.extend(log_lines[-100:])
    else:
        lines.append('no log file')

    OUT_PATH.write_text('\n'.join(lines), encoding='utf8')
    print(f'Reporte generado: {OUT_PATH}')


if __name__ == '__main__':
    main()
