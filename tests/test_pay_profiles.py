from datetime import date

import pandas as pd
import pytest

import pay_profiles


def _profile(pay_frequency="monthly", gross=3000.0, pretax=100.0, taxes=50.0,
             start="2024-01-01", end=None) -> dict:
    return {
        "pay_frequency": pay_frequency,
        "gross_per_period": gross,
        "pretax_deductions_per_period": pretax,
        "taxes_per_period": taxes,
        "effective_start": pd.Timestamp(start),
        "effective_end": pd.Timestamp(end) if end else pd.NaT,
    }


def _profiles_df(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def _expected_daily(pay_frequency: str, amount_per_period: float) -> float:
    return amount_per_period * pay_profiles.PAY_FREQUENCIES[pay_frequency] / pay_profiles.DAYS_PER_YEAR


class TestNetPerPeriod:
    def test_subtracts_deductions_and_taxes_from_gross(self):
        profile = pd.Series({"gross_per_period": 3000.0, "pretax_deductions_per_period": 500.0,
                              "taxes_per_period": 600.0})
        assert pay_profiles.net_per_period(profile) == 1900.0


class TestProratedTotals:
    def test_empty_profiles_returns_zeros(self):
        result = pay_profiles.prorated_totals(pd.DataFrame(), date(2024, 1, 1), date(2024, 1, 31))
        assert result == {"pretax_deductions": 0.0, "taxes": 0.0}

    def test_profile_covering_full_range_with_no_end_date(self):
        profiles = _profiles_df(_profile(pretax=100.0, taxes=50.0, start="2024-01-01"))
        result = pay_profiles.prorated_totals(profiles, date(2024, 1, 1), date(2024, 1, 31))
        days = 31
        assert result["pretax_deductions"] == pytest.approx(_expected_daily("monthly", 100.0) * days)
        assert result["taxes"] == pytest.approx(_expected_daily("monthly", 50.0) * days)

    def test_profile_starting_mid_range_only_counts_overlap(self):
        profiles = _profiles_df(_profile(pretax=100.0, taxes=0.0, start="2024-01-15"))
        result = pay_profiles.prorated_totals(profiles, date(2024, 1, 1), date(2024, 1, 31))
        days = 17  # Jan 15 through Jan 31 inclusive
        assert result["pretax_deductions"] == pytest.approx(_expected_daily("monthly", 100.0) * days)

    def test_profile_entirely_before_range_contributes_nothing(self):
        profiles = _profiles_df(_profile(pretax=100.0, start="2023-01-01", end="2023-12-31"))
        result = pay_profiles.prorated_totals(profiles, date(2024, 1, 1), date(2024, 1, 31))
        assert result == {"pretax_deductions": 0.0, "taxes": 0.0}

    def test_profile_entirely_after_range_contributes_nothing(self):
        profiles = _profiles_df(_profile(pretax=100.0, start="2024-06-01"))
        result = pay_profiles.prorated_totals(profiles, date(2024, 1, 1), date(2024, 1, 31))
        assert result == {"pretax_deductions": 0.0, "taxes": 0.0}

    def test_gap_between_profiles_is_not_covered(self):
        # Profile A: Jan 1-10 (10 days). Profile B: Jan 20-31 (12 days).
        # Jan 11-19 (9 days) is covered by neither and should contribute 0.
        profiles = _profiles_df(
            _profile(pretax=100.0, taxes=0.0, start="2024-01-01", end="2024-01-10"),
            _profile(pretax=100.0, taxes=0.0, start="2024-01-20"),
        )
        result = pay_profiles.prorated_totals(profiles, date(2024, 1, 1), date(2024, 1, 31))
        expected = _expected_daily("monthly", 100.0) * (10 + 12)
        assert result["pretax_deductions"] == pytest.approx(expected)

    def test_multiple_profiles_sum_independently(self):
        solo_a = pay_profiles.prorated_totals(
            _profiles_df(_profile(pretax=100.0, taxes=10.0, start="2024-01-01", end="2024-01-10")),
            date(2024, 1, 1), date(2024, 1, 31),
        )
        solo_b = pay_profiles.prorated_totals(
            _profiles_df(_profile(pretax=200.0, taxes=20.0, start="2024-01-20")),
            date(2024, 1, 1), date(2024, 1, 31),
        )
        combined = pay_profiles.prorated_totals(
            _profiles_df(
                _profile(pretax=100.0, taxes=10.0, start="2024-01-01", end="2024-01-10"),
                _profile(pretax=200.0, taxes=20.0, start="2024-01-20"),
            ),
            date(2024, 1, 1), date(2024, 1, 31),
        )
        assert combined["pretax_deductions"] == pytest.approx(
            solo_a["pretax_deductions"] + solo_b["pretax_deductions"]
        )
        assert combined["taxes"] == pytest.approx(solo_a["taxes"] + solo_b["taxes"])
