import pandas as pd
import pytest

import chat_tools


@pytest.fixture
def tx():
    return pd.DataFrame({
        "tx_date": pd.to_datetime([
            "2024-01-01", "2024-01-15", "2024-02-01", "2024-02-10", "2024-02-15",
        ]),
        "description": ["Grocery Store", "Paycheck", "Coffee Shop", "Rent Payment", "Refund"],
        "category": ["Groceries", "Income", "Coffee Shops", "Rent", "Shopping"],
        "amount": [-100.00, 2000.00, -4.567, -1500.00, 25.00],
        "status": ["Posted", "Posted", "Pending", "Posted", "Posted"],
        "account": ["Checking", "Checking", "Credit Card", "Checking", "Credit Card"],
        "owner": ["You", "You", "Partner", "You", "Partner"],
    })


class TestSearchTransactions:
    def test_no_filters_returns_everything_most_recent_first(self, tx):
        result = chat_tools.search_transactions(tx)
        assert result["matched_count"] == 5
        assert result["returned_count"] == 5
        assert result["truncated"] is False
        assert result["transactions"][0]["description"] == "Refund"
        assert result["transactions"][-1]["description"] == "Grocery Store"

    def test_description_contains_is_case_insensitive(self, tx):
        result = chat_tools.search_transactions(tx, description_contains="coffee")
        assert result["matched_count"] == 1
        assert result["transactions"][0]["description"] == "Coffee Shop"

    def test_category_exact_match_case_insensitive(self, tx):
        result = chat_tools.search_transactions(tx, category="groceries")
        assert result["matched_count"] == 1

    def test_account_filter(self, tx):
        result = chat_tools.search_transactions(tx, account="credit card")
        assert result["matched_count"] == 2

    def test_owner_filter(self, tx):
        result = chat_tools.search_transactions(tx, owner="partner")
        assert result["matched_count"] == 2

    def test_status_filter(self, tx):
        result = chat_tools.search_transactions(tx, status="pending")
        assert result["matched_count"] == 1
        assert result["transactions"][0]["description"] == "Coffee Shop"

    def test_date_range_is_inclusive(self, tx):
        result = chat_tools.search_transactions(tx, start_date="2024-02-01", end_date="2024-02-10")
        assert {t["description"] for t in result["transactions"]} == {"Coffee Shop", "Rent Payment"}

    def test_spend_over_threshold_uses_signed_max_amount(self, tx):
        # "spend over $30" -> amount <= -30
        result = chat_tools.search_transactions(tx, max_amount=-30)
        assert {t["description"] for t in result["transactions"]} == {"Grocery Store", "Rent Payment"}

    def test_income_over_threshold_uses_signed_min_amount(self, tx):
        result = chat_tools.search_transactions(tx, min_amount=500)
        assert result["matched_count"] == 1
        assert result["transactions"][0]["description"] == "Paycheck"

    def test_total_amount_covers_all_matches_even_when_truncated(self, tx):
        result = chat_tools.search_transactions(tx, limit=1)
        assert result["matched_count"] == 5
        assert result["returned_count"] == 1
        assert result["truncated"] is True
        assert result["total_amount"] == pytest.approx(round(-100 + 2000 - 4.567 - 1500 + 25, 2))

    def test_limit_below_one_still_returns_at_least_one_row(self, tx):
        result = chat_tools.search_transactions(tx, limit=0)
        assert result["returned_count"] == 1

    def test_limit_above_cap_is_clamped_to_max_results(self, tx):
        result = chat_tools.search_transactions(tx, limit=10_000)
        assert result["returned_count"] == len(tx)

    def test_amount_rounded_and_date_formatted_in_output(self, tx):
        result = chat_tools.search_transactions(tx, description_contains="coffee")
        row = result["transactions"][0]
        assert row["amount"] == -4.57
        assert row["tx_date"] == "2024-02-01"

    def test_no_matches_returns_empty_with_zero_total(self, tx):
        result = chat_tools.search_transactions(tx, category="nonexistent")
        assert result == {
            "matched_count": 0,
            "returned_count": 0,
            "truncated": False,
            "total_amount": 0.0,
            "transactions": [],
        }
