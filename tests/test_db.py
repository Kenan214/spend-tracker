import pandas as pd
import pytest

import db


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "spend.db")
    connection = db.get_connection()
    yield connection
    connection.close()


def _tx_df(**overrides) -> pd.DataFrame:
    row = {
        "tx_date": "2024-01-15",
        "description": "Coffee Shop",
        "original_description": "COFFEE SHOP #123",
        "category": "Coffee Shops",
        "amount": -4.50,
        "status": "Posted",
        "account": "Chase Checking",
        "dedup_key": "abc123",
        "imported_at": "2024-01-15T00:00:00+00:00",
    }
    row.update(overrides)
    return pd.DataFrame([row])


class TestTransactions:
    def test_upsert_inserts_new_rows(self, conn):
        inserted, updated = db.upsert_transactions(conn, _tx_df())
        assert (inserted, updated) == (1, 0)
        assert len(db.fetch_transactions(conn)) == 1

    def test_upsert_updates_by_dedup_key(self, conn):
        db.upsert_transactions(conn, _tx_df())
        inserted, updated = db.upsert_transactions(
            conn, _tx_df(description="Coffee Shop (fixed)", category="Food & Dining", status="Pending")
        )
        assert (inserted, updated) == (0, 1)

        row = db.fetch_transactions(conn).iloc[0]
        assert row["description"] == "Coffee Shop (fixed)"
        assert row["category"] == "Food & Dining"
        assert row["status"] == "Pending"

    def test_upsert_does_not_overwrite_amount_or_account(self, conn):
        db.upsert_transactions(conn, _tx_df())
        db.upsert_transactions(conn, _tx_df(amount=-999, account="Some Other Account"))

        row = db.fetch_transactions(conn).iloc[0]
        assert row["amount"] == -4.50
        assert row["account"] == "Chase Checking"

    def test_fetch_transactions_orders_by_date(self, conn):
        db.upsert_transactions(conn, _tx_df(tx_date="2024-02-01", dedup_key="k2"))
        db.upsert_transactions(conn, _tx_df(tx_date="2024-01-01", dedup_key="k1"))
        df = db.fetch_transactions(conn)
        assert list(df["dedup_key"]) == ["k1", "k2"]


class TestBills:
    def test_add_and_fetch_bill(self, conn):
        db.add_bill(conn, "Netflix", 15.49, "Subscriptions", "monthly")
        df = db.fetch_bills(conn)
        assert len(df) == 1
        assert df.iloc[0]["name"] == "Netflix"
        assert df.iloc[0]["expected_amount"] == 15.49

    def test_fetch_bills_orders_by_amount_desc(self, conn):
        db.add_bill(conn, "Netflix", 15.49, "Subscriptions", "monthly")
        db.add_bill(conn, "Rent", 2000.0, "Rent", "monthly")
        df = db.fetch_bills(conn)
        assert list(df["name"]) == ["Rent", "Netflix"]

    def test_update_bill(self, conn):
        db.add_bill(conn, "Netflix", 15.49, "Subscriptions", "monthly")
        bill_id = int(db.fetch_bills(conn).iloc[0]["id"])
        db.update_bill(conn, bill_id, "Netflix", 22.99, "Subscriptions", "monthly")
        assert db.fetch_bills(conn).iloc[0]["expected_amount"] == 22.99

    def test_delete_bill(self, conn):
        db.add_bill(conn, "Netflix", 15.49, "Subscriptions", "monthly")
        bill_id = int(db.fetch_bills(conn).iloc[0]["id"])
        db.delete_bill(conn, bill_id)
        assert db.fetch_bills(conn).empty


class TestAccountOwners:
    def test_set_and_fetch_owner(self, conn):
        db.set_account_owner(conn, "Chase Checking", "You")
        df = db.fetch_account_owners(conn)
        assert dict(zip(df["account"], df["owner"])) == {"Chase Checking": "You"}

    def test_set_owner_upserts(self, conn):
        db.set_account_owner(conn, "Chase Checking", "You")
        db.set_account_owner(conn, "Chase Checking", "Partner")
        df = db.fetch_account_owners(conn)
        assert len(df) == 1
        assert df.iloc[0]["owner"] == "Partner"


class TestCategoryOverrides:
    def test_set_and_fetch_override(self, conn):
        db.set_category_override(conn, "COFFEE SHOP #123", "Food & Dining")
        df = db.fetch_category_overrides(conn)
        assert dict(zip(df["merchant_pattern"], df["category"])) == {"COFFEE SHOP #123": "Food & Dining"}

    def test_set_override_upserts_by_pattern(self, conn):
        db.set_category_override(conn, "COFFEE SHOP #123", "Food & Dining")
        db.set_category_override(conn, "COFFEE SHOP #123", "Coffee Shops")
        df = db.fetch_category_overrides(conn)
        assert len(df) == 1
        assert df.iloc[0]["category"] == "Coffee Shops"

    def test_delete_override(self, conn):
        db.set_category_override(conn, "COFFEE SHOP #123", "Food & Dining")
        db.delete_category_override(conn, "COFFEE SHOP #123")
        assert db.fetch_category_overrides(conn).empty


class TestPayProfiles:
    def test_add_and_fetch_profile(self, conn):
        db.add_pay_profile(conn, "biweekly", 3000.0, 500.0, 600.0, "2024-01-01", None)
        df = db.fetch_pay_profiles(conn)
        assert len(df) == 1
        assert df.iloc[0]["pay_frequency"] == "biweekly"
        assert pd.isna(df.iloc[0]["effective_end"])

    def test_update_profile(self, conn):
        db.add_pay_profile(conn, "biweekly", 3000.0, 500.0, 600.0, "2024-01-01", None)
        profile_id = int(db.fetch_pay_profiles(conn).iloc[0]["id"])
        db.update_pay_profile(conn, profile_id, "biweekly", 3200.0, 500.0, 650.0, "2024-01-01", "2024-06-30")
        row = db.fetch_pay_profiles(conn).iloc[0]
        assert row["gross_per_period"] == 3200.0
        assert row["effective_end"] == pd.Timestamp("2024-06-30")

    def test_delete_profile(self, conn):
        db.add_pay_profile(conn, "biweekly", 3000.0, 500.0, 600.0, "2024-01-01", None)
        profile_id = int(db.fetch_pay_profiles(conn).iloc[0]["id"])
        db.delete_pay_profile(conn, profile_id)
        assert db.fetch_pay_profiles(conn).empty
