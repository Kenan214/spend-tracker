import pandas as pd
import pytest

import bills


def _spend_rows(description: str, dates: list[str], amounts: list[float], category: str = "Subscriptions"):
    return pd.DataFrame({
        "description": [description] * len(dates),
        "category": [category] * len(dates),
        "tx_date": pd.to_datetime(dates),
        "amount": amounts,
    })


class TestDetectCandidates:
    def test_detects_monthly_recurring_charge(self):
        spend = _spend_rows(
            "Netflix",
            ["2024-01-01", "2024-02-01", "2024-03-02", "2024-04-01"],
            [-15.99, -15.99, -15.99, -15.99],
        )
        candidates = bills.detect_candidates(spend, known_names=set())
        assert len(candidates) == 1
        row = candidates.iloc[0]
        assert row["description"] == "Netflix"
        assert row["cadence"] == "monthly"
        assert row["occurrences"] == 4
        assert row["avg_amount"] == pytest.approx(15.99)

    def test_excludes_known_bill_names_case_insensitively(self):
        spend = _spend_rows(
            "Netflix",
            ["2024-01-01", "2024-02-01", "2024-03-02", "2024-04-01"],
            [-15.99, -15.99, -15.99, -15.99],
        )
        candidates = bills.detect_candidates(spend, known_names={"netflix"})
        assert candidates.empty

    def test_excludes_below_min_occurrences(self):
        spend = _spend_rows("Netflix", ["2024-01-01", "2024-02-01"], [-15.99, -15.99])
        candidates = bills.detect_candidates(spend, known_names=set())
        assert candidates.empty

    def test_excludes_high_amount_variation(self):
        spend = _spend_rows(
            "Variable Charge",
            ["2024-01-01", "2024-02-01", "2024-03-02", "2024-04-01"],
            [-10.0, -10.0, -10.0, -50.0],
        )
        candidates = bills.detect_candidates(spend, known_names=set())
        assert candidates.empty

    def test_excludes_irregular_cadence(self):
        spend = _spend_rows(
            "Random Merchant",
            ["2024-01-01", "2024-01-11", "2024-01-21", "2024-01-31"],
            [-20.0, -20.0, -20.0, -20.0],
        )
        candidates = bills.detect_candidates(spend, known_names=set())
        assert candidates.empty

    def test_empty_input_returns_empty_with_expected_columns(self):
        empty = pd.DataFrame(columns=["description", "category", "tx_date", "amount"])
        candidates = bills.detect_candidates(empty, known_names=set())
        assert candidates.empty
        assert list(candidates.columns) == bills.CANDIDATE_COLUMNS

    def test_sorted_by_avg_amount_descending(self):
        dates = ["2024-01-01", "2024-02-01", "2024-03-02", "2024-04-01"]
        cheap = _spend_rows("Cheap Sub", dates, [-5.0] * 4)
        pricey = _spend_rows("Pricey Sub", dates, [-50.0] * 4)
        spend = pd.concat([cheap, pricey], ignore_index=True)
        candidates = bills.detect_candidates(spend, known_names=set())
        assert list(candidates["description"]) == ["Pricey Sub", "Cheap Sub"]


class TestMonthlyEquivalent:
    @pytest.mark.parametrize("cadence,multiplier", [
        ("weekly", 4.345),
        ("biweekly", 2.1725),
        ("monthly", 1.0),
        ("quarterly", 1 / 3),
        ("annual", 1 / 12),
    ])
    def test_known_cadences(self, cadence, multiplier):
        assert bills.monthly_equivalent(100, cadence) == pytest.approx(100 * multiplier)

    def test_unknown_cadence_defaults_to_unchanged_amount(self):
        assert bills.monthly_equivalent(100, "fortnightly") == 100
