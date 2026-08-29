import pytest

import budget_guidelines as bg


class TestBucketFor:
    @pytest.mark.parametrize("category,expected", [
        ("Groceries", "Needs"),
        ("Restaurants", "Wants"),
        ("Uncategorized", "Unmapped"),
        ("Category Pending", "Unmapped"),
    ])
    def test_fifty_thirty_twenty(self, category, expected):
        assert bg.bucket_for(bg.FIFTY_THIRTY_TWENTY, category) == expected

    @pytest.mark.parametrize("category,expected", [
        ("Rent", "Housing"),
        ("Gas", "Transportation"),
        ("Groceries", "Food"),
        ("Shopping", "Unmapped"),
    ])
    def test_category_specific(self, category, expected):
        assert bg.bucket_for(bg.CATEGORY_SPECIFIC, category) == expected


class TestFrameworkRegistry:
    def test_frameworks_keyed_by_their_own_key(self):
        for key, framework in bg.FRAMEWORKS.items():
            assert framework.key == key

    def test_fifty_thirty_twenty_targets_sum_to_one(self):
        assert sum(bg.FIFTY_THIRTY_TWENTY.default_targets.values()) == pytest.approx(1.0)

    @pytest.mark.parametrize("framework", bg.FRAMEWORKS.values(), ids=lambda f: f.key)
    def test_bucket_order_matches_declared_buckets(self, framework):
        assert set(framework.bucket_order) == set(framework.default_targets)
        assert set(framework.bucket_order) == set(framework.direction)
        assert set(framework.bucket_order) == set(framework.income_basis)

    @pytest.mark.parametrize("framework", bg.FRAMEWORKS.values(), ids=lambda f: f.key)
    def test_direction_and_income_basis_values_are_valid(self, framework):
        assert set(framework.direction.values()) <= {"max", "min"}
        assert set(framework.income_basis.values()) <= {"net", "gross"}

    @pytest.mark.parametrize("framework", bg.FRAMEWORKS.values(), ids=lambda f: f.key)
    def test_category_map_targets_are_real_buckets_or_savings(self, framework):
        # "Savings" is derived from net income directly, never looked up via
        # category_map, so it's legitimately absent from bucket_order.
        allowed = set(framework.bucket_order) | {"Savings"}
        assert set(framework.category_map.values()) <= allowed
