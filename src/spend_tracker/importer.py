"""CSV import and normalization.

Expects USAA-style exports with columns:
Date, Description, Original Description, Category, Amount, Status
"""
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

COLUMN_MAP = {
    "Date": "tx_date",
    "Description": "description",
    "Original Description": "original_description",
    "Category": "category",
    "Amount": "amount",
    "Status": "status",
}

DATE_SUFFIX_RE = re.compile(r"_\d{2}-\d{2}-\d{4}$")


def account_name_from_filename(path: Path) -> str:
    stem = DATE_SUFFIX_RE.sub("", path.stem)
    return stem.replace("_", " ").replace("-", " ").strip().title()


def _dedup_key(row: pd.Series) -> str:
    # A sequence number distinguishes genuinely repeated same-day/same-amount
    # transactions at the same merchant (e.g. three identical $8.40 charges)
    # from re-imports of the same file, as long as export order is stable.
    raw = f"{row['tx_date']}|{row['original_description']}|{row['amount']}|{row['_occurrence']}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.rename(columns=COLUMN_MAP)
    missing = set(COLUMN_MAP.values()) - set(df.columns)
    if missing:
        raise ValueError(f"{path.name} is missing expected columns: {sorted(missing)}")

    df["tx_date"] = pd.to_datetime(df["tx_date"]).dt.strftime("%Y-%m-%d")
    df["account"] = account_name_from_filename(path)
    df["_occurrence"] = df.groupby(["tx_date", "original_description", "amount"]).cumcount()
    df["dedup_key"] = df.apply(_dedup_key, axis=1)
    df["imported_at"] = datetime.now(timezone.utc).isoformat()
    return df[
        [
            "tx_date",
            "description",
            "original_description",
            "category",
            "amount",
            "status",
            "account",
            "dedup_key",
            "imported_at",
        ]
    ]


def find_csv_files(raw_dir: Path) -> list[Path]:
    return sorted(raw_dir.glob("*.csv"))
