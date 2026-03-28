import sqlite3
from momentum_pullback_v2.config import BACKTEST_REPORT, DB_PATH


def session_report():
    if not DB_PATH.exists():
        return 'no db'
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute('select count(*), coalesce(sum(case when pnl>0 then 1 else 0 end),0), coalesce(sum(pnl),0), coalesce(avg(pnl),0) from trades').fetchone()
    conn.close()
    trades, wins, total_pnl, avg_pnl = rows
    wr = wins / trades * 100 if trades else 0.0
    return f'trades={trades} wins={wins} wr={wr:.2f} pnl={total_pnl:.6f} avg={avg_pnl:.6f}'
