import sqlite3
from pathlib import Path

DB_PATH = Path('tick_vampire_v3/trades.db')
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            direction TEXT,
            entry_price REAL,
            exit_price REAL,
            size REAL,
            pnl REAL,
            fee REAL,
            exit_reason TEXT,
            session TEXT,
            balance_after REAL
        )
    ''')
    conn.commit()
    conn.close()

def insert_trade(row: tuple):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'INSERT INTO trades (timestamp, direction, entry_price, exit_price, size, pnl, fee, exit_reason, session, balance_after) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        row,
    )
    conn.commit()
    conn.close()
