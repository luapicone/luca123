import sqlite3
from momentum_pullback_v2.config import DB_PATH, DATA_DIR


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        create table if not exists trades (
            id integer primary key autoincrement,
            timestamp text,
            symbol text,
            direction text,
            entry_price real,
            exit_price real,
            size real,
            pnl real,
            fee real,
            exit_reason text,
            balance_after real,
            score real,
            retrace real,
            context_rsi real,
            momentum_pct real,
            pullback_len integer,
            hold_minutes real,
            mfe real,
            mae real,
            peak_progress real
        )
    ''')
    existing = {row[1] for row in conn.execute("pragma table_info(trades)").fetchall()}
    migrations = {
        'score': 'alter table trades add column score real',
        'retrace': 'alter table trades add column retrace real',
        'context_rsi': 'alter table trades add column context_rsi real',
        'momentum_pct': 'alter table trades add column momentum_pct real',
        'pullback_len': 'alter table trades add column pullback_len integer',
        'hold_minutes': 'alter table trades add column hold_minutes real',
        'mfe': 'alter table trades add column mfe real',
        'mae': 'alter table trades add column mae real',
        'peak_progress': 'alter table trades add column peak_progress real',
    }
    for col, stmt in migrations.items():
        if col not in existing:
            conn.execute(stmt)
    conn.commit()
    conn.close()


def insert_trade(row):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'insert into trades (timestamp,symbol,direction,entry_price,exit_price,size,pnl,fee,exit_reason,balance_after,score,retrace,context_rsi,momentum_pct,pullback_len,hold_minutes,mfe,mae,peak_progress) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        row,
    )
    conn.commit()
    conn.close()
