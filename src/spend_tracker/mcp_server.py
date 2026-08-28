"""Local MCP server for the in-app chat advisor — read-only v1 slice of the
"Future state: in-app chat advisor for transaction classification, spend
Q&A & affordability decisions" plan in README.md.

Exposes exactly one tool, `search_transactions` (see chat_tools.py for the
filtering logic), over the same transaction data — category overrides and
account owners already applied — the rest of the app uses. No write tool
yet (no `apply_category_override`): this process only ever reads
data/spend.db via db.py, it can't touch anything else on disk or run
commands. The chat CLI invocation that launches this server (see
app.py's `run_chat_turn`) is separately locked to exactly this one tool
(`--tools ""` to drop all built-in tools including Bash, `--allowedTools`
naming only this server's tool) — this module being read-only is a second,
independent layer of the same restriction, not the only one.

Launched by the `claude` CLI itself via `--mcp-config` (one subprocess per
chat turn); not started directly by app.py. Run standalone to sanity-check
the tool responds:
    .venv/bin/python3 src/spend_tracker/mcp_server.py
(it will sit waiting for stdio MCP messages — Ctrl-C to exit).
"""
from mcp.server.mcpserver import MCPServer

import category_overrides as category_overrides_module
import chat_tools
import db
import owners as owners_module

mcp = MCPServer("spend_tracker")


def _load_transactions():
    conn = db.get_connection()
    tx = db.fetch_transactions(conn)
    overrides_df = db.fetch_category_overrides(conn)
    tx = category_overrides_module.apply_overrides(tx, overrides_df)
    owners_df = db.fetch_account_owners(conn)
    return owners_module.with_owner(tx, owners_df)


@mcp.tool()
def search_transactions(
    description_contains: str | None = None,
    category: str | None = None,
    account: str | None = None,
    owner: str | None = None,
    status: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    limit: int = chat_tools.MAX_RESULTS,
) -> dict:
    """Search the user's imported bank/card transactions.

    All filters are optional and combine with AND; omit a filter to leave
    it unrestricted. `description_contains` is a case-insensitive substring
    match on the merchant description. `category`, `account`, `owner`, and
    `status` (e.g. "Posted"/"Pending") are case-insensitive exact matches.
    `start_date`/`end_date` are "YYYY-MM-DD", inclusive.

    IMPORTANT: `amount` is signed — negative means money OUT (spend),
    positive means money IN (income/refund/credit). "spend over $30" means
    amount <= -30, so pass max_amount=-30 (not min_amount=30). "income over
    $500" means min_amount=500.

    Returns matched_count (total matches), returned_count (rows in this
    page), truncated (more matches exist than were returned — narrow the
    filters, e.g. by date range or description, rather than raising limit
    past its cap), total_amount (sum over ALL matches, not just the
    returned page — trust this for totals even when truncated), and
    transactions (the page itself, most recent first).
    """
    tx = _load_transactions()
    return chat_tools.search_transactions(
        tx,
        description_contains=description_contains,
        category=category,
        account=account,
        owner=owner,
        status=status,
        start_date=start_date,
        end_date=end_date,
        min_amount=min_amount,
        max_amount=max_amount,
        limit=limit,
    )


if __name__ == "__main__":
    mcp.run()
