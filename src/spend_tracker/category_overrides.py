"""Manual category overrides — v1 slice of the "Manual category overrides for
Uncategorized / Category Pending rows" next-step in README.md.

Overrides are keyed by merchant pattern (a transaction's exact `description`
string, matched case-insensitively), not by individual transaction id, so a
fix applies to every past and future occurrence of that merchant and
survives re-imports — re-importing a CSV can overwrite `category` from the
bank's own data, but never touches this table. This is also the mechanism
the future in-app chat advisor is meant to write into (see README), so
overrides aren't restricted to rows currently Uncategorized/Category
Pending — the UI just limits which merchants you're prompted to fix.
"""
import pandas as pd


def apply_overrides(tx: pd.DataFrame, overrides_df: pd.DataFrame) -> pd.DataFrame:
    """Replace `category` for any row whose description matches a stored
    merchant pattern, case-insensitively. Rows with no matching override
    keep their original category.
    """
    if overrides_df.empty:
        return tx
    mapping = dict(zip(overrides_df["merchant_pattern"].str.lower(), overrides_df["category"]))
    tx = tx.copy()
    override_category = tx["description"].str.lower().map(mapping)
    tx["category"] = override_category.fillna(tx["category"])
    return tx
