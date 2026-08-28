"""SQLite storage for imported transactions."""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Packaged builds (see packaging/) set SPEND_TRACKER_DATA_DIR so user data
# lives outside the app bundle, in a location that's writable regardless of
# where the bundle sits and that survives replacing the bundle with a newer
# build. Local dev (running straight from a repo checkout) leaves it unset
# and keeps data alongside the source, as before.
PROJECT_ROOT = Path(os.environ["SPEND_TRACKER_DATA_DIR"]) if os.environ.get("SPEND_TRACKER_DATA_DIR") \
    else Path(__file__).resolve().parents[2]
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

CREATE TABLE IF NOT EXISTS bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    expected_amount REAL NOT NULL,
    category TEXT,
    cadence TEXT NOT NULL DEFAULT 'monthly',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_owners (
    account TEXT PRIMARY KEY,
    owner TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS category_overrides (
    merchant_pattern TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pay_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pay_frequency TEXT NOT NULL,
    gross_per_period REAL NOT NULL,
    pretax_deductions_per_period REAL NOT NULL DEFAULT 0,
    taxes_per_period REAL NOT NULL DEFAULT 0,
    effective_start TEXT NOT NULL,
    effective_end TEXT,
    created_at TEXT NOT NULL
);
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


def add_bill(
    conn: sqlite3.Connection, name: str, expected_amount: float, category: str, cadence: str
) -> None:
    conn.execute(
        """
        INSERT INTO bills (name, expected_amount, category, cadence, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (name, expected_amount, category, cadence, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def fetch_bills(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM bills ORDER BY expected_amount DESC", conn)


def update_bill(
    conn: sqlite3.Connection, bill_id: int, name: str, expected_amount: float, category: str, cadence: str
) -> None:
    conn.execute(
        """
        UPDATE bills SET name = ?, expected_amount = ?, category = ?, cadence = ?
        WHERE id = ?
        """,
        (name, expected_amount, category, cadence, bill_id),
    )
    conn.commit()


def delete_bill(conn: sqlite3.Connection, bill_id: int) -> None:
    conn.execute("DELETE FROM bills WHERE id = ?", (bill_id,))
    conn.commit()


def fetch_account_owners(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql("SELECT account, owner FROM account_owners", conn)


def set_account_owner(conn: sqlite3.Connection, account: str, owner: str) -> None:
    conn.execute(
        """
        INSERT INTO account_owners (account, owner) VALUES (?, ?)
        ON CONFLICT(account) DO UPDATE SET owner=excluded.owner
        """,
        (account, owner),
    )
    conn.commit()


def fetch_category_overrides(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql(
        "SELECT merchant_pattern, category FROM category_overrides ORDER BY merchant_pattern", conn
    )


def set_category_override(conn: sqlite3.Connection, merchant_pattern: str, category: str) -> None:
    conn.execute(
        """
        INSERT INTO category_overrides (merchant_pattern, category, created_at) VALUES (?, ?, ?)
        ON CONFLICT(merchant_pattern) DO UPDATE SET category=excluded.category
        """,
        (merchant_pattern, category, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def delete_category_override(conn: sqlite3.Connection, merchant_pattern: str) -> None:
    conn.execute("DELETE FROM category_overrides WHERE merchant_pattern = ?", (merchant_pattern,))
    conn.commit()


def add_pay_profile(
    conn: sqlite3.Connection,
    pay_frequency: str,
    gross_per_period: float,
    pretax_deductions_per_period: float,
    taxes_per_period: float,
    effective_start: str,
    effective_end: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO pay_profiles
            (pay_frequency, gross_per_period, pretax_deductions_per_period, taxes_per_period,
             effective_start, effective_end, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pay_frequency, gross_per_period, pretax_deductions_per_period, taxes_per_period,
            effective_start, effective_end, datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def fetch_pay_profiles(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql(
        "SELECT * FROM pay_profiles ORDER BY effective_start",
        conn, parse_dates=["effective_start", "effective_end"],
    )


def update_pay_profile(
    conn: sqlite3.Connection,
    profile_id: int,
    pay_frequency: str,
    gross_per_period: float,
    pretax_deductions_per_period: float,
    taxes_per_period: float,
    effective_start: str,
    effective_end: str | None,
) -> None:
    conn.execute(
        """
        UPDATE pay_profiles SET
            pay_frequency = ?, gross_per_period = ?, pretax_deductions_per_period = ?,
            taxes_per_period = ?, effective_start = ?, effective_end = ?
        WHERE id = ?
        """,
        (
            pay_frequency, gross_per_period, pretax_deductions_per_period, taxes_per_period,
            effective_start, effective_end, profile_id,
        ),
    )
    conn.commit()


def delete_pay_profile(conn: sqlite3.Connection, profile_id: int) -> None:
    conn.execute("DELETE FROM pay_profiles WHERE id = ?", (profile_id,))
    conn.commit()
