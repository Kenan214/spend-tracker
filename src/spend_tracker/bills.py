"""Recurring-transaction detection — v1 slice of the "Future state: bills
view with manual overrides" plan in README.md.

Flags transactions with the same description recurring at a roughly
regular cadence and a similar amount as candidate bills, surfaced for the
user to confirm. Never auto-adds anything to the bill registry — that
stays a manual, explicit action (see db.add_bill).
"""
import pandas as pd

CADENCE_DAYS = {
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
    "quarterly": 91,
    "annual": 365,
}
CADENCE_TOLERANCE = 0.25  # +/- 25% of the cadence's typical day-gap
MIN_OCCURRENCES = 3
MAX_AMOUNT_VARIATION = 0.15  # coefficient of variation (std / mean) allowed

CANDIDATE_COLUMNS = ["description", "category", "cadence", "avg_amount", "occurrences", "last_date"]


def _closest_cadence(median_gap_days: float) -> str | None:
    for cadence, days in CADENCE_DAYS.items():
        if abs(median_gap_days - days) <= days * CADENCE_TOLERANCE:
            return cadence
    return None


def detect_candidates(spend_only: pd.DataFrame, known_names: set[str]) -> pd.DataFrame:
    """Group spend by description and flag groups that look like recurring bills.

    `known_names` (existing bill names) are excluded case-insensitively so
    already-registered bills don't get re-suggested.
    """
    if spend_only.empty:
        return pd.DataFrame(columns=CANDIDATE_COLUMNS)

    known_lower = {n.lower() for n in known_names}
    rows = []
    for description, group in spend_only.groupby("description"):
        if description.lower() in known_lower or len(group) < MIN_OCCURRENCES:
            continue

        dates = group["tx_date"].sort_values()
        gaps = dates.diff().dt.days.dropna()
        if gaps.empty:
            continue
        cadence = _closest_cadence(gaps.median())
        if cadence is None:
            continue

        amounts = group["amount"].abs()
        mean_amount = amounts.mean()
        if mean_amount == 0 or amounts.std() / mean_amount > MAX_AMOUNT_VARIATION:
            continue

        rows.append({
            "description": description,
            "category": group["category"].mode().iat[0],
            "cadence": cadence,
            "avg_amount": mean_amount,
            "occurrences": len(group),
            "last_date": dates.max(),
        })

    if not rows:
        return pd.DataFrame(columns=CANDIDATE_COLUMNS)
    return pd.DataFrame(rows).sort_values("avg_amount", ascending=False).reset_index(drop=True)


# Multiplier to express each cadence as a monthly-equivalent amount.
MONTHLY_EQUIVALENT = {
    "weekly": 4.345,
    "biweekly": 2.1725,
    "monthly": 1.0,
    "quarterly": 1 / 3,
    "annual": 1 / 12,
}


def monthly_equivalent(amount: float, cadence: str) -> float:
    return amount * MONTHLY_EQUIVALENT.get(cadence, 1.0)
