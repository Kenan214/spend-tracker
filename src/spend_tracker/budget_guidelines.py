"""50/30/20 budget-guideline benchmark — v1 scope.

Deliberately narrow slice of the fuller "Future state: benchmark spend
against recommended budget guidelines" plan in README.md: bank-deposit
income only (no pay-stub entry), a single hardcoded framework (50/30/20,
not selectable), and a plain category->bucket map (not a config file).
Those remain real follow-ups, not oversights.
"""

# USAA-style categories, split into 50/30/20's "Needs" vs "Wants". Anything
# not listed here (including Uncategorized/Category Pending) falls into
# "Unmapped" rather than being silently guessed into either bucket.
NEEDS_CATEGORIES = {
    "Mortgage & Rent", "Rent", "Utilities", "Gas & Electric", "Electric", "Water",
    "Internet & Cable", "Internet", "Phone", "Cell Phone", "Mobile Phone", "Groceries",
    "Health & Wellness", "Doctor", "Eyecare", "Pharmacy", "Insurance", "Auto Insurance",
    "Health Insurance", "Life Insurance", "Gas", "Gas/Fuel", "Auto Payment",
    "Loan Payment", "Student Loan", "Child Care", "Day Care", "Service & Parts",
    "Pet Food & Supplies", "Education", "Home Supplies",
}

WANTS_CATEGORIES = {
    "Restaurants", "Fast Food", "Food & Dining", "Coffee Shops", "Shopping",
    "Clothing", "Entertainment", "Movies & Dvds", "Movies & DVDs", "Music",
    "Hobbies", "Sports", "Sporting Goods", "Electronics & Software",
    "Personal Care", "Hair", "Spa & Massage", "Gym", "Travel", "Vacation",
    "Air Travel", "Hotel", "Rental Car & Taxi", "Subscriptions",
    "Alcohol & Bars", "Gifts & Donations", "Charity", "Home Improvement",
    "Lawn & Garden", "Home", "Television", "Books", "Newspapers & Magazines",
    "Kids Activities", "Parking",
}

TARGET_PCT = {"Needs": 0.50, "Wants": 0.30, "Savings": 0.20}


def bucket_for(category: str) -> str:
    if category in NEEDS_CATEGORIES:
        return "Needs"
    if category in WANTS_CATEGORIES:
        return "Wants"
    return "Unmapped"
