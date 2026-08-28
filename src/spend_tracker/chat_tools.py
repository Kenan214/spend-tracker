"""Read-only transaction search for the in-app chat advisor — read-only v1
slice of the "Future state: in-app chat advisor for transaction
classification, spend Q&A & affordability decisions" plan in README.md.

Pure filtering logic over the same transaction data (category overrides +
account owners already applied) the rest of the app uses, so chat answers
match what the Overview/Household tabs show. Kept separate from
`mcp_server.py` (the MCP protocol plumbing) so this is testable as plain
pandas code. Deliberately searches *all* imported transactions rather than
whatever the sidebar happens to be filtered to right now — the chat exposes
its own filter args per query instead.
"""
import pandas as pd

MAX_RESULTS = 200

RESULT_COLUMNS = ["tx_date", "description", "category", "amount", "status", "account", "owner"]


def search_transactions(
    tx: pd.DataFrame,
    description_contains: str | None = None,
    category: str | None = None,
    account: str | None = None,
    owner: str | None = None,
    status: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    limit: int = MAX_RESULTS,
) -> dict:
    """Filter `tx` by the given criteria (all optional; omitted = unfiltered).

    `amount` is signed, same as the underlying data: negative = money out
    (spend), positive = money in (income/refund/credit). E.g. "spend over
    $30" means amount <= -30, so pass max_amount=-30.

    Returns a dict with `matched_count` (total matches), `returned_count`
    (rows actually included), `truncated` (True if matches exceed `limit`),
    `total_amount` (sum over *all* matches, not just the returned page, so
    totals stay correct even when truncated), and `transactions` (the page
    of matching rows, most recent first).
    """
    df = tx
    if description_contains:
        df = df[df["description"].str.contains(description_contains, case=False, na=False)]
    if category:
        df = df[df["category"].str.lower() == category.lower()]
    if account:
        df = df[df["account"].str.lower() == account.lower()]
    if owner:
        df = df[df["owner"].str.lower() == owner.lower()]
    if status:
        df = df[df["status"].str.lower() == status.lower()]
    if start_date:
        df = df[df["tx_date"] >= pd.Timestamp(start_date)]
    if end_date:
        df = df[df["tx_date"] <= pd.Timestamp(end_date)]
    if min_amount is not None:
        df = df[df["amount"] >= min_amount]
    if max_amount is not None:
        df = df[df["amount"] <= max_amount]

    df = df.sort_values("tx_date", ascending=False)
    matched_count = len(df)
    total_amount = round(float(df["amount"].sum()), 2) if matched_count else 0.0

    page_limit = max(1, min(limit, MAX_RESULTS))
    page = df.head(page_limit)[RESULT_COLUMNS].copy()
    page["tx_date"] = page["tx_date"].dt.strftime("%Y-%m-%d")
    page["amount"] = page["amount"].round(2)

    return {
        "matched_count": matched_count,
        "returned_count": len(page),
        "truncated": matched_count > len(page),
        "total_amount": total_amount,
        "transactions": page.to_dict("records"),
    }
