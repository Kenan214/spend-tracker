"""Account ownership tags — v1 slice of the "Future state: multi-account
household view with a per-person split" plan in README.md.

An account's owner (e.g. "You" vs "Partner") is independent of the account/
bank label `importer.account_name_from_filename` derives from the CSV
filename — two accounts at the same bank can belong to different owners.
Ownership is stored in the `account_owners` table (see db.py) and assigned
in the app rather than inferred from filenames or a config file, so a
dropped-in CSV works regardless of naming convention.
"""
import pandas as pd

UNASSIGNED = "Unassigned"


def known_owners(owners_df: pd.DataFrame) -> list[str]:
    if owners_df.empty:
        return []
    return sorted(owners_df["owner"].unique())


def unassigned_accounts(accounts: list[str], owners_df: pd.DataFrame) -> list[str]:
    mapped = set(owners_df["account"]) if not owners_df.empty else set()
    return [a for a in accounts if a not in mapped]


def with_owner(tx: pd.DataFrame, owners_df: pd.DataFrame) -> pd.DataFrame:
    """Attach an `owner` column, defaulting to UNASSIGNED for any account
    that hasn't been tagged yet.
    """
    mapping = dict(zip(owners_df["account"], owners_df["owner"])) if not owners_df.empty else {}
    tx = tx.copy()
    tx["owner"] = tx["account"].map(mapping).fillna(UNASSIGNED)
    return tx
