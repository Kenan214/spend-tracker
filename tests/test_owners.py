import pandas as pd

import owners


def _owners_df(accounts, owner_names):
    return pd.DataFrame({"account": accounts, "owner": owner_names})


class TestKnownOwners:
    def test_empty_returns_empty_list(self):
        assert owners.known_owners(pd.DataFrame(columns=["account", "owner"])) == []

    def test_returns_sorted_unique_owners(self):
        df = _owners_df(["Checking", "Savings", "Credit Card"], ["Partner", "You", "You"])
        assert owners.known_owners(df) == ["Partner", "You"]


class TestUnassignedAccounts:
    def test_all_unassigned_when_no_owners_set(self):
        assert owners.unassigned_accounts(["Checking", "Savings"], pd.DataFrame(columns=["account", "owner"])) == [
            "Checking", "Savings",
        ]

    def test_excludes_accounts_with_an_owner(self):
        df = _owners_df(["Checking"], ["You"])
        assert owners.unassigned_accounts(["Checking", "Savings"], df) == ["Savings"]


class TestWithOwner:
    def test_defaults_to_unassigned_for_unmapped_accounts(self):
        tx = pd.DataFrame({"account": ["Checking", "Savings"]})
        result = owners.with_owner(tx, pd.DataFrame(columns=["account", "owner"]))
        assert list(result["owner"]) == [owners.UNASSIGNED, owners.UNASSIGNED]

    def test_applies_known_owner_mapping(self):
        tx = pd.DataFrame({"account": ["Checking", "Savings"]})
        owners_df = _owners_df(["Checking"], ["You"])
        result = owners.with_owner(tx, owners_df)
        assert list(result["owner"]) == ["You", owners.UNASSIGNED]

    def test_does_not_mutate_input_dataframe(self):
        tx = pd.DataFrame({"account": ["Checking"]})
        owners.with_owner(tx, _owners_df(["Checking"], ["You"]))
        assert "owner" not in tx.columns
