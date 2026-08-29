import pandas as pd

import category_overrides


def _tx(descriptions, categories):
    return pd.DataFrame({"description": descriptions, "category": categories})


class TestApplyOverrides:
    def test_empty_overrides_returns_original_categories(self):
        tx = _tx(["Coffee Shop"], ["Uncategorized"])
        result = category_overrides.apply_overrides(tx, pd.DataFrame(columns=["merchant_pattern", "category"]))
        assert list(result["category"]) == ["Uncategorized"]

    def test_matches_case_insensitively(self):
        tx = _tx(["COFFEE SHOP #123"], ["Uncategorized"])
        overrides = pd.DataFrame({"merchant_pattern": ["coffee shop #123"], "category": ["Coffee Shops"]})
        result = category_overrides.apply_overrides(tx, overrides)
        assert result.iloc[0]["category"] == "Coffee Shops"

    def test_non_matching_rows_keep_original_category(self):
        tx = _tx(["Coffee Shop", "Gas Station"], ["Uncategorized", "Gas"])
        overrides = pd.DataFrame({"merchant_pattern": ["coffee shop"], "category": ["Coffee Shops"]})
        result = category_overrides.apply_overrides(tx, overrides)
        assert list(result["category"]) == ["Coffee Shops", "Gas"]

    def test_does_not_mutate_input_dataframe(self):
        tx = _tx(["Coffee Shop"], ["Uncategorized"])
        overrides = pd.DataFrame({"merchant_pattern": ["coffee shop"], "category": ["Coffee Shops"]})
        category_overrides.apply_overrides(tx, overrides)
        assert tx.iloc[0]["category"] == "Uncategorized"
