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
            balance_after real
        )
    ''')
    conn.commit()
    conn.close()


def insert_trade(row):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('insert into trades (timestamp,symbol,direction,entry_price,exit_price,size,pnl,fee,exit_reason,balance_after) values (?,?,?,?,?,?,?,?,?,?)', row)
    conn.commit()
    conn.close()
