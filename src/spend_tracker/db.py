"""SQLite storage for imported transactions."""
import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "spend.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tx_date TEXT NOT NULL,
    description TEXT,
    original_description TEXT,
    category TEXT,
    amount REAL NOT NULL,
    status TEXT,
    account TEXT NOT NULL,
    dedup_key TEXT NOT NULL UNIQUE,
    imported_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions (tx_date);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions (category);
"""


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def upsert_transactions(conn: sqlite3.Connection, df: pd.DataFrame) -> tuple[int, int]:
    """Insert new transactions, update existing ones by dedup_key.

    Returns (inserted, updated) counts.
    """
    existing = pd.read_sql("SELECT dedup_key FROM transactions", conn)
    existing_keys = set(existing["dedup_key"])

    inserted = int((~df["dedup_key"].isin(existing_keys)).sum())
    updated = len(df) - inserted

    conn.executemany(
        """
        INSERT INTO transactions
            (tx_date, description, original_description, category, amount, status, account, dedup_key, imported_at)
        VALUES (:tx_date, :description, :original_description, :category, :amount, :status, :account, :dedup_key, :imported_at)
        ON CONFLICT(dedup_key) DO UPDATE SET
            description=excluded.description,
            category=excluded.category,
            status=excluded.status,
            imported_at=excluded.imported_at
        """,
        df.to_dict("records"),
    )
    conn.commit()
    return inserted, updated


def fetch_transactions(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM transactions ORDER BY tx_date", conn, parse_dates=["tx_date"])
    return df
