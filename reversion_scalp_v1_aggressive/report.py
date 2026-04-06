import sqlite3
from reversion_scalp_v1_aggressive.config import DB_PATH


def session_report():
    if not DB_PATH.exists():
        return 'no db'
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute('select count(*), coalesce(sum(case when pnl>0 then 1 else 0 end),0), coalesce(sum(pnl),0), coalesce(avg(pnl),0), coalesce(avg(mfe),0), coalesce(avg(mae),0), coalesce(avg(hold_minutes),0) from trades').fetchone()
    conn.close()
    trades, wins, total_pnl, avg_pnl, avg_mfe, avg_mae, avg_hold = rows
    wr = wins / trades * 100 if trades else 0.0
    return f'trades={trades} wins={wins} wr={wr:.2f} pnl={total_pnl:.6f} avg={avg_pnl:.6f} avg_mfe={avg_mfe:.6f} avg_mae={avg_mae:.6f} avg_hold={avg_hold:.2f}'
