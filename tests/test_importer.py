from pathlib import Path

import pandas as pd
import pytest

import importer


class TestAccountNameFromFilename:
    def test_strips_date_suffix_and_titlecases(self):
        assert importer.account_name_from_filename(Path("chase_checking_01-15-2024.csv")) == "Chase Checking"

    def test_handles_hyphenated_names(self):
        assert importer.account_name_from_filename(Path("usaa-credit-card.csv")) == "Usaa Credit Card"

    def test_no_date_suffix_is_left_alone(self):
        assert importer.account_name_from_filename(Path("savings.csv")) == "Savings"


def _write_csv(path: Path, rows: list[dict]) -> Path:
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _row(**overrides) -> dict:
    row = {
        "Date": "2024-01-15",
        "Description": "Coffee Shop",
        "Original Description": "COFFEE SHOP #123",
        "Category": "Coffee Shops",
        "Amount": -4.50,
        "Status": "Posted",
    }
    row.update(overrides)
    return row


class TestLoadCsv:
    def test_missing_expected_columns_raises(self, tmp_path):
        path = _write_csv(tmp_path / "acct.csv", [{"Date": "2024-01-15", "Amount": -1}])
        with pytest.raises(ValueError, match="missing expected columns"):
            importer.load_csv(path)

    def test_normalizes_columns_and_derives_account(self, tmp_path):
        path = _write_csv(tmp_path / "chase_checking_01-15-2024.csv", [_row()])
        df = importer.load_csv(path)
        assert list(df.columns) == [
            "tx_date", "description", "original_description", "category",
            "amount", "status", "account", "dedup_key", "imported_at",
        ]
        assert df.iloc[0]["account"] == "Chase Checking"
        assert df.iloc[0]["tx_date"] == "2024-01-15"

    def test_dedup_key_is_stable_for_identical_input(self, tmp_path):
        path = _write_csv(tmp_path / "acct.csv", [_row()])
        first = importer.load_csv(path).iloc[0]["dedup_key"]
        second = importer.load_csv(path).iloc[0]["dedup_key"]
        assert first == second

    def test_repeated_identical_transactions_get_distinct_dedup_keys(self, tmp_path):
        # Three genuinely separate $4.50 charges at the same place on the
        # same day must not collapse into one row on import.
        path = _write_csv(tmp_path / "acct.csv", [_row(), _row(), _row()])
        df = importer.load_csv(path)
        assert df["dedup_key"].nunique() == 3

    def test_different_amount_or_date_changes_dedup_key(self, tmp_path):
        path = _write_csv(
            tmp_path / "acct.csv",
            [_row(), _row(Amount=-9.00), _row(Date="2024-01-16")],
        )
        df = importer.load_csv(path)
        assert df["dedup_key"].nunique() == 3


class TestFindCsvFiles:
    def test_finds_only_csvs_sorted(self, tmp_path):
        (tmp_path / "b.csv").write_text("x")
        (tmp_path / "a.csv").write_text("x")
        (tmp_path / "notes.txt").write_text("x")
        found = importer.find_csv_files(tmp_path)
        assert [p.name for p in found] == ["a.csv", "b.csv"]

    def test_empty_dir_returns_empty_list(self, tmp_path):
        assert importer.find_csv_files(tmp_path) == []
