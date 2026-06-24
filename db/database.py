"""VISI v2 — Database"""
import sqlite3, config

def get_conn():
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_conn(); c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS candles_5min (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        instrument TEXT NOT NULL, date TEXT NOT NULL,
        timestamp TEXT NOT NULL, open REAL, high REAL, low REAL, close REAL, volume INTEGER,
        UNIQUE(instrument, timestamp));

    CREATE TABLE IF NOT EXISTS candles_1min (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        instrument TEXT NOT NULL, date TEXT NOT NULL,
        timestamp TEXT NOT NULL, open REAL, high REAL, low REAL, close REAL, volume INTEGER,
        UNIQUE(instrument, timestamp));

    CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        instrument TEXT, date TEXT, time TEXT,
        direction TEXT, vsa_signal TEXT, rvol REAL,
        layer1 TEXT, layer2 TEXT, layer3 TEXT, layer4_pcr REAL,
        groq_decision TEXT, groq_confidence TEXT, groq_reason TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')));

    CREATE TABLE IF NOT EXISTS virtual_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        instrument TEXT, date TEXT,
        entry_time TEXT, exit_time TEXT,
        direction TEXT, strike TEXT,
        entry_price REAL, sl_price REAL, target_price REAL, exit_price REAL,
        sl_points REAL, pnl_points REAL, pnl_rupees REAL,
        lots INTEGER DEFAULT 1, lot_size INTEGER,
        exit_reason TEXT, vsa_signal TEXT, rvol REAL,
        layers_passed INTEGER DEFAULT 7, status TEXT DEFAULT 'OPEN',
        notes TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')));

    CREATE TABLE IF NOT EXISTS backtest_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        instrument TEXT, run_date TEXT,
        from_date TEXT, to_date TEXT,
        total_trades INTEGER, wins INTEGER, losses INTEGER,
        win_rate REAL, total_pnl REAL,
        avg_win REAL, avg_loss REAL,
        max_drawdown REAL, profit_factor REAL,
        sharpe_ratio REAL, calmar_ratio REAL,
        params_json TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')));

    CREATE TABLE IF NOT EXISTS backtest_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER, instrument TEXT, date TEXT,
        entry_time TEXT, exit_time TEXT, direction TEXT,
        entry_price REAL, sl_price REAL, target_price REAL, exit_price REAL,
        pnl_points REAL, exit_reason TEXT, vsa_signal TEXT, rvol REAL,
        FOREIGN KEY(run_id) REFERENCES backtest_runs(id));

    CREATE TABLE IF NOT EXISTS daily_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        instrument TEXT, date TEXT,
        trades INTEGER, wins INTEGER, losses INTEGER,
        total_pnl_pts REAL, total_pnl_rs REAL,
        UNIQUE(instrument, date));
    """)
    conn.commit(); conn.close()
    print("[DB] Tables initialised.")
