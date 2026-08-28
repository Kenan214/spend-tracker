"""Budget-guideline frameworks — benchmark spend against common rules of thumb.

Selectable-framework slice of the "Future state: benchmark spend against
recommended budget guidelines" plan in README.md. `income_basis` records
which income figure (net take-home vs. gross) each bucket's target is
traditionally expressed against — see the "Income basis" design note and
pay_profiles.py, which supplies the optional gross/net split. A plain
in-code category->bucket map per framework (not a config file) remains a
real follow-up, not an oversight.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Framework:
    key: str
    name: str
    summary: str
    pros: str
    cons: str
    # category -> bucket name, for every bucket except "Savings" (which is
    # always derived from net income, not a category lookup).
    category_map: dict[str, str] = field(default_factory=dict)
    # bucket -> default target fraction of income (editable in the UI).
    default_targets: dict[str, float] = field(default_factory=dict)
    # bucket -> "max" (flag when actual exceeds target, e.g. Needs/Housing)
    # or "min" (flag when actual falls short, e.g. Savings).
    direction: dict[str, str] = field(default_factory=dict)
    # bucket -> "net" or "gross": which income figure this bucket's target
    # is traditionally expressed as a percentage of. 50/30/20 is a net
    # take-home framework throughout; the classic per-category ceilings
    # (housing/transportation/food) are traditionally gross-income rules,
    # while their Savings bucket is still evaluated against net. See the
    # "Income basis" design note in README.md.
    income_basis: dict[str, str] = field(default_factory=dict)
    bucket_order: tuple[str, ...] = ()


# USAA-style categories, split into 50/30/20's "Needs" vs "Wants". Anything
# not listed here (including Uncategorized/Category Pending) falls into
# "Unmapped" rather than being silently guessed into either bucket.
_FIFTY_THIRTY_TWENTY_MAP = {
    cat: "Needs" for cat in (
        "Mortgage & Rent", "Rent", "Utilities", "Gas & Electric", "Electric", "Water",
        "Internet & Cable", "Internet", "Phone", "Cell Phone", "Mobile Phone", "Groceries",
        "Health & Wellness", "Doctor", "Eyecare", "Pharmacy", "Insurance", "Auto Insurance",
        "Health Insurance", "Life Insurance", "Gas", "Gas/Fuel", "Auto Payment",
        "Loan Payment", "Student Loan", "Child Care", "Day Care", "Service & Parts",
        "Pet Food & Supplies", "Education", "Home Supplies",
    )
} | {
    cat: "Wants" for cat in (
        "Restaurants", "Fast Food", "Food & Dining", "Coffee Shops", "Shopping",
        "Clothing", "Entertainment", "Movies & Dvds", "Movies & DVDs", "Music",
        "Hobbies", "Sports", "Sporting Goods", "Electronics & Software",
        "Personal Care", "Hair", "Spa & Massage", "Gym", "Travel", "Vacation",
        "Air Travel", "Hotel", "Rental Car & Taxi", "Subscriptions",
        "Alcohol & Bars", "Gifts & Donations", "Charity", "Home Improvement",
        "Lawn & Garden", "Home", "Television", "Books", "Newspapers & Magazines",
        "Kids Activities", "Parking",
    )
}

FIFTY_THIRTY_TWENTY = Framework(
    key="50_30_20",
    name="50/30/20",
    summary="50% Needs, 30% Wants, 20% Savings/debt paydown, as a share of income.",
    pros="Simple: three buckets, easy to reason about and track month to month.",
    cons="Coarse — a $4k/mo mortgage and a $1.2k/mo mortgage both just count as "
         "\"Needs\", so it can't tell you which specific bill is the problem.",
    category_map=_FIFTY_THIRTY_TWENTY_MAP,
    default_targets={"Needs": 0.50, "Wants": 0.30, "Savings": 0.20},
    direction={"Needs": "max", "Wants": "max", "Savings": "min"},
    income_basis={"Needs": "net", "Wants": "net", "Savings": "net"},
    bucket_order=("Needs", "Wants", "Savings"),
)

# Per-category recommended ceilings commonly cited by financial advisors.
_CATEGORY_SPECIFIC_MAP = {
    cat: "Housing" for cat in (
        "Mortgage & Rent", "Rent", "Utilities", "Gas & Electric", "Electric", "Water",
        "Internet & Cable", "Internet", "Home Supplies", "Home Improvement",
        "Lawn & Garden", "Home",
    )
} | {
    cat: "Transportation" for cat in (
        "Gas", "Gas/Fuel", "Auto Payment", "Service & Parts", "Parking",
        "Rental Car & Taxi", "Auto Insurance",
    )
} | {
    cat: "Food" for cat in (
        "Groceries", "Restaurants", "Fast Food", "Food & Dining", "Coffee Shops",
        "Alcohol & Bars",
    )
}

CATEGORY_SPECIFIC = Framework(
    key="category_specific",
    name="Category-specific rules",
    summary="Per-category ceilings: Housing ≤30%, Transportation ≤15%, "
            "Food ≤15%, Savings ≥20% of income.",
    pros="More precise than 50/30/20 — points at which specific category is "
         "actually the problem instead of a lumped \"Needs\" total.",
    cons="Assumes a \"typical\" household budget split; categories outside "
         "Housing/Transportation/Food/Savings (shopping, entertainment, "
         "travel, etc.) aren't benchmarked at all.",
    category_map=_CATEGORY_SPECIFIC_MAP,
    default_targets={"Housing": 0.30, "Transportation": 0.15, "Food": 0.15, "Savings": 0.20},
    direction={"Housing": "max", "Transportation": "max", "Food": "max", "Savings": "min"},
    income_basis={
        "Housing": "gross", "Transportation": "gross", "Food": "gross", "Savings": "net",
    },
    bucket_order=("Housing", "Transportation", "Food", "Savings"),
)

FRAMEWORKS = {f.key: f for f in (FIFTY_THIRTY_TWENTY, CATEGORY_SPECIFIC)}


def bucket_for(framework: Framework, category: str) -> str:
    return framework.category_map.get(category, "Unmapped")
