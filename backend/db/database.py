"""
数据库连接和模型定义
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from pathlib import Path
import os

DB_PATH = Path(__file__).parent.parent / "data" / "stock_analyzer.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库，创建所有表"""
    Base.metadata.create_all(bind=engine)


SCHEMA_SQL = """
-- 股票基础信息
CREATE TABLE IF NOT EXISTS stocks (
    code      TEXT PRIMARY KEY,
    name      TEXT,
    list_date TEXT,
    segment   TEXT
);

-- 日K线原始数据
CREATE TABLE IF NOT EXISTS daily_kline (
    code    TEXT,
    date    TEXT,
    open    REAL,
    high    REAL,
    low     REAL,
    close   REAL,
    volume  REAL,
    PRIMARY KEY (code, date)
);

-- 指标定义表
CREATE TABLE IF NOT EXISTS indicator_definitions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT UNIQUE,
    formula    TEXT,
    params     TEXT,
    category   TEXT,
    created_at TEXT
);

-- 日线指标值
CREATE TABLE IF NOT EXISTS daily_indicators (
    code         TEXT,
    date         TEXT,
    indicator_id INTEGER,
    value        REAL,
    PRIMARY KEY (code, date, indicator_id)
);

-- U1买点定义参数（用户配置）
CREATE TABLE IF NOT EXISTS u1_config (
    id         INTEGER PRIMARY KEY,
    name       TEXT,
    hold_days  INTEGER DEFAULT 5,
    profit_pct REAL    DEFAULT 2.0,
    buy_price  TEXT    DEFAULT 'MA5',
    enabled    INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
);

-- 探索会话
CREATE TABLE IF NOT EXISTS exploration_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT,
    batch_id     TEXT,
    u1_config_id INTEGER,
    start_time   TEXT,
    end_time     TEXT,
    status       TEXT,
    result       TEXT
);

-- 逻辑组合候选（探索过程）
CREATE TABLE IF NOT EXISTS logic_candidates (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     INTEGER,
    stage          TEXT,
    logic_desc     TEXT,
    formula_expr   TEXT,
    precision      REAL,
    coverage_count INTEGER,
    u2_count       INTEGER,
    created_at     TEXT
);

-- 优选公式存档（最终结果）
CREATE TABLE IF NOT EXISTS best_formulas (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT,
    u1_config_id   INTEGER,
    logic_desc     TEXT,
    formula_expr   TEXT,
    a1             REAL,
    a2             REAL,
    a3             REAL,
    explored_at     TEXT,
    opportunity_dates TEXT
);

-- 用户自选股票列表
CREATE TABLE IF NOT EXISTS watchlist (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    code     TEXT UNIQUE,
    name     TEXT,
    added_at TEXT
);

-- 系统设置
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- 插入默认U1配置
INSERT OR IGNORE INTO u1_config (id, name, hold_days, profit_pct, buy_price, enabled, created_at, updated_at)
VALUES (1, '默认配置', 5, 2.0, 'MA5', 1, datetime('now'), datetime('now'));
"""


def create_tables():
    """直接执行建表SQL（SQLite不支持IF NOT EXISTS所有DDL，分开执行）"""
    from sqlalchemy import text
    with engine.connect() as conn:
        # 分批执行建表
        tables = [
            """CREATE TABLE IF NOT EXISTS stocks (
                code TEXT PRIMARY KEY, name TEXT, list_date TEXT, segment TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS daily_kline (
                code TEXT, date TEXT, open REAL, high REAL, low REAL,
                close REAL, volume REAL, PRIMARY KEY (code, date)
            )""",
            """CREATE TABLE IF NOT EXISTS indicator_definitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE,
                formula TEXT, params TEXT, category TEXT, created_at TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS daily_indicators (
                code TEXT, date TEXT, indicator_id INTEGER, value REAL,
                PRIMARY KEY (code, date, indicator_id)
            )""",
            """CREATE TABLE IF NOT EXISTS u1_config (
                id INTEGER PRIMARY KEY, name TEXT, hold_days INTEGER DEFAULT 5,
                profit_pct REAL DEFAULT 2.0, buy_price TEXT DEFAULT 'MA5',
                enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS exploration_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, batch_id TEXT,
                u1_config_id INTEGER, start_time TEXT, end_time TEXT,
                status TEXT, result TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS logic_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, stage TEXT,
                logic_desc TEXT, formula_expr TEXT, precision REAL,
                coverage_count INTEGER, u2_count INTEGER, created_at TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS best_formulas (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, u1_config_id INTEGER,
                logic_desc TEXT, formula_expr TEXT, a1 REAL, a2 REAL, a3 REAL, explored_at TEXT,
                opportunity_dates TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, name TEXT, added_at TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS exploration_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, code TEXT,
                status TEXT, total_seconds INTEGER, candidates_total INTEGER,
                segments_data TEXT, best_formula TEXT, best_precision REAL,
                best_coverage INTEGER, iterations INTEGER, final_message TEXT, created_at TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS formula_overrides (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, logic_desc TEXT,
                formula_expr TEXT, a1 REAL, a2 REAL, a3 REAL,
                source TEXT DEFAULT 'manual', created_at TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS indicator_params (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                category TEXT DEFAULT 'custom',
                param_config TEXT NOT NULL,
                description TEXT,
                created_at TEXT,
                updated_at TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS formula_combinations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                formula_expr TEXT NOT NULL,
                logic_desc TEXT,
                indicator_refs TEXT,
                created_at TEXT,
                updated_at TEXT
            )""",
        ]
        for sql in tables:
            conn.execute(text(sql))

        # Idempotent: add opportunity_dates column if missing from best_formulas (for existing DBs)
        try:
            conn.execute(text("ALTER TABLE best_formulas ADD COLUMN opportunity_dates TEXT"))
        except Exception:
            pass  # column already exists

        # Idempotent: add u1_dates column (buy point dates) if missing
        try:
            conn.execute(text("ALTER TABLE best_formulas ADD COLUMN u1_dates TEXT"))
        except Exception:
            pass  # column already exists

        # Idempotent: add source column if missing from best_formulas
        try:
            conn.execute(text("ALTER TABLE best_formulas ADD COLUMN source TEXT DEFAULT 'explore'"))
        except Exception:
            pass  # column already exists

        # Idempotent: add unique index on best_formulas.code (for upsert support)
        try:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_best_formulas_code ON best_formulas(code)"))
        except Exception:
            pass  # index already exists

        # 插入默认U1配置
        conn.execute(text("""INSERT OR IGNORE INTO u1_config
            (id, name, hold_days, profit_pct, buy_price, enabled, created_at, updated_at)
            VALUES (1, '默认配置', 5, 2.0, 'MA5', 1, datetime('now'), datetime('now'))"""))
        conn.commit()

        # Migration: ensure new tables exist in existing databases
        for new_table_sql in [
            """CREATE TABLE IF NOT EXISTS indicator_params (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence_number TEXT UNIQUE,
                name TEXT UNIQUE NOT NULL,
                category TEXT DEFAULT 'custom',
                param_config TEXT NOT NULL,
                description TEXT,
                created_at TEXT,
                updated_at TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS formula_combinations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence_number TEXT UNIQUE,
                name TEXT NOT NULL,
                formula_expr TEXT NOT NULL,
                logic_desc TEXT,
                indicator_refs TEXT,
                created_at TEXT,
                updated_at TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS backtest_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                formula_id INTEGER,
                stock_code TEXT,
                start_date TEXT,
                end_date TEXT,
                initial_capital REAL DEFAULT 100000,
                position_type TEXT DEFAULT 'percent_capital',
                position_value REAL DEFAULT 10,
                stop_loss_type TEXT DEFAULT 'percent',
                stop_loss_value REAL DEFAULT -5,
                take_profit_type TEXT DEFAULT 'percent',
                take_profit_value REAL DEFAULT 15,
                entry_price_type TEXT DEFAULT 'open',
                created_at TEXT,
                updated_at TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_id INTEGER,
                stock_code TEXT,
                total_trades INTEGER,
                win_trades INTEGER,
                loss_trades INTEGER,
                total_return REAL,
                max_drawdown REAL,
                sharpe_ratio REAL,
                profit_factor REAL,
                equity_curve TEXT,
                trade_log TEXT,
                created_at TEXT
            )"""
        ]:
            try:
                conn.execute(text(new_table_sql))
            except Exception:
                pass

        # Migration: add sequence_number columns if missing (for existing tables)
        try:
            conn.execute(text("ALTER TABLE indicator_params ADD COLUMN sequence_number TEXT"))
        except Exception:
            pass  # column already exists
        try:
            conn.execute(text("ALTER TABLE formula_combinations ADD COLUMN sequence_number TEXT"))
        except Exception:
            pass  # column already exists

        # Migration: add sequence_number unique index if missing
        try:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_indicator_params_seq ON indicator_params(sequence_number)"))
        except Exception:
            pass
        try:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_formula_combinations_seq ON formula_combinations(sequence_number)"))
        except Exception:
            pass

        conn.commit()


if __name__ == "__main__":
    create_tables()
    print("数据库初始化完成:", DB_PATH)