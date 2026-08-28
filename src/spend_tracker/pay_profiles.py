"""Optional pay-stub detail — v1 slice of the "Income basis" design note
under "Future state: benchmark spend against recommended budget
guidelines" in README.md.

Bank-deposit income (`Income`/`Paycheck` transactions) is a sufficient
default and needs no entry here. When a pay profile is entered, it lets
the Budget Guideline tab (a) gross up net take-home for guidelines that
are traditionally expressed as a % of GROSS income (e.g. "housing <=30%
of income"), and (b) count payroll-deducted retirement/HSA/insurance
contributions as real savings, since that money is withheld before the
paycheck hits the bank and never appears in bank data at all.

Deliberately simplified vs. an itemized pay stub: pretax deductions
(retirement + HSA/FSA + insurance premiums) are lumped into one number,
and taxes (federal/state/FICA) into another, rather than tracked
separately. That means a payroll-paid insurance premium gets folded into
the "Savings" bucket alongside real retirement contributions, which
overstates savings if insurance is a meaningful share of that number —
an accepted simplification for faster data entry, not an oversight.

Entries carry an effective-date range (not one row per paycheck) since
salary and benefit elections change (raises, open enrollment).
"""
from datetime import date

import pandas as pd

# Pay frequency -> periods per year, used to annualize a per-period dollar
# amount before prorating it across a filtered date range.
PAY_FREQUENCIES = {
    "weekly": 52,
    "biweekly": 26,
    "semimonthly": 24,
    "monthly": 12,
}

DAYS_PER_YEAR = 365.25


def net_per_period(profile: pd.Series) -> float:
    return (
        profile["gross_per_period"]
        - profile["pretax_deductions_per_period"]
        - profile["taxes_per_period"]
    )


def prorated_totals(profiles: pd.DataFrame, start_date: date, end_date: date) -> dict:
    """Sum each profile's daily-rate pretax-deduction/tax amounts over
    however much of [start_date, end_date] that profile was in effect.

    A day not covered by any profile (no profiles entered, or a gap
    between effective-date ranges) contributes nothing — the result
    understates the true total rather than guessing, so partial pay-stub
    coverage degrades gracefully instead of skewing the numbers.
    """
    pretax_total = 0.0
    taxes_total = 0.0
    if profiles.empty:
        return {"pretax_deductions": pretax_total, "taxes": taxes_total}

    for _, profile in profiles.iterrows():
        periods_per_year = PAY_FREQUENCIES[profile["pay_frequency"]]
        daily_pretax = profile["pretax_deductions_per_period"] * periods_per_year / DAYS_PER_YEAR
        daily_taxes = profile["taxes_per_period"] * periods_per_year / DAYS_PER_YEAR

        profile_start = profile["effective_start"].date()
        profile_end = (
            profile["effective_end"].date() if pd.notna(profile["effective_end"]) else end_date
        )
        overlap_start = max(start_date, profile_start)
        overlap_end = min(end_date, profile_end)
        if overlap_start > overlap_end:
            continue
        days = (overlap_end - overlap_start).days + 1
        pretax_total += daily_pretax * days
        taxes_total += daily_taxes * days

    return {"pretax_deductions": pretax_total, "taxes": taxes_total}
