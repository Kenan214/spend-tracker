# Spend Tracker

A local app + UI for visualizing personal spend over time, imported from bank/card
CSV exports. Everything runs and stores data locally — nothing leaves your machine.

## Install (no development tools needed)

1. Download `SpendTracker-<version>-macOS.zip` from the
   [latest release](https://github.com/Kenan214/spend-tracker/releases/latest)
   and unzip it (double-click in Finder if it doesn't auto-unzip).
2. Move `Spend Tracker.app` wherever you'd like (e.g. `/Applications`), then
   double-click it. It's not signed by an identified Apple developer (that
   requires a paid Apple Developer account), so macOS will block it the
   first time with a message like *"Apple could not verify... free of
   malware."* This is expected — to allow it:
   - Click **Done** (not "Move to Trash") on that dialog.
   - Open **System Settings → Privacy & Security**, scroll down to the
     Security section, and you'll see *"Spend Tracker" was blocked...*
     with an **Open Anyway** button next to it. Click it, confirm again,
     and it launches.
   - This one-time approval is only needed the first launch; every launch
     after that is a normal double-click. It's also the *last* time you'll
     need to do this manually — see "Staying up to date" below.
3. First launch takes a minute or two — it's installing Python dependencies
   in the background (a "First launch — setting up…" notification appears).
   Requires [Python 3](https://python.org) to already be installed; if it's
   missing you'll get a clear alert saying so, rather than a silent failure.

Your data (`spend.db`, imported CSVs) lives in
`~/Library/Application Support/Spend Tracker/`, separate from the app itself
— it's untouched if you later update to a newer release.

### Staying up to date

Once you've approved and launched the app the first time, it keeps itself
up to date automatically — no more re-downloading from GitHub or clicking
through **System Settings → Privacy & Security** for later versions.

Every launch, the app quietly checks GitHub for a newer release in the
background (at most once every 30 minutes) and, if one exists, downloads
and verifies it without interrupting what you're doing. The next time you
launch the app, it swaps in the new version before opening (you may notice
a brief extra moment on that one launch) and you're running the update —
still with no Gatekeeper prompt, since the app itself downloaded the file
rather than a browser or Finder. This relies on `com.apple.quarantine` (the
attribute that triggers Gatekeeper's "unidentified developer" block) only
being attached by quarantine-aware tools like Safari or Finder's
unzip-from-download — a plain background download by an app you've already
approved never gets it, the same trick real third-party updaters (e.g.
Sparkle) rely on.

This is entirely best-effort: no internet, GitHub being unreachable, a
corrupted download, etc. never blocks or breaks the currently-installed
version — it just means you'll keep running the current version until the
next successful check. There's no user-facing setting for this yet; it
can't be turned off.

## Cutting a release

```bash
packaging/build_release.sh v0.1.2
gh release create v0.1.2 --title v0.1.2 --generate-notes
gh release upload v0.1.2 dist/SpendTracker-v0.1.2-macOS.zip
```
`build_release.sh` produces a self-contained `Spend Tracker.app` (source
bundled inside `Contents/Resources/app/`, so it doesn't depend on this repo
checkout) in `dist/`, distinct from the dev-mode app built directly in the
repo root above. It also stamps the given version into
`Contents/Resources/app/VERSION` (the self-updater's source of truth for
"what's currently installed") and into `Info.plist`'s
`CFBundleShortVersionString`/`CFBundleVersion` (previously hardcoded to a
stale `"1.0"`/`"1"` for every build).

The asset name (`SpendTracker-<version>-macOS.zip`) and the fact that
`releases/latest` is unauthenticated-fetchable now that the repo is public
are both load-bearing for the self-updater (`packaging/update_check.sh`),
which parses exactly that filename pattern out of the GitHub Releases API
response — don't rename the asset format without updating it too.

## Setup (development)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage (development)

**As a Mac app (recommended):** double-click `Spend Tracker.app` in this folder
(or move/alias it to `/Applications` or the Dock). It opens as a native window —
no browser tab or terminal needed — and sets up the Python environment on first
run if it doesn't exist yet.

If you ever move this repo to a different path, rebuild the app so it points at
the new location:
```bash
rm -rf "Spend Tracker.app"
osacompile -o "Spend Tracker.app" launcher.applescript
```
(`launcher.applescript` and `launch_app.sh` both assume the repo lives where it
currently does — `chmod +x launch_app.sh` if it ever loses its execute bit.)

**From the terminal (browser tab instead of a native window):**
```bash
source .venv/bin/activate
streamlit run src/spend_tracker/app.py
```

**Either way**, import a CSV export by dragging it onto the uploader in the
sidebar, or by dropping the file into `data/raw/` directly — both land in the
same place and get imported into a local SQLite database (`data/spend.db`).
Then filter by date range, account, category, and pending/posted status.

Re-importing the same file, or a newer export that overlaps with data you
already have (e.g. dropping in a full Jan–Dec export in December after
already importing Jan–Aug), is safe — transactions are deduplicated by
(date, original description, amount, occurrence), and existing rows are
updated in place (useful when a pending transaction later posts with a
finalized category). Only genuinely new transactions get added.

## Expected CSV format

Currently supports USAA-style exports with these columns:

```
Date, Description, Original Description, Category, Amount, Status
```

The account name shown in the UI is derived from the filename (e.g.
`usaa_bank_01-08-2026.csv` → "Usaa Bank"). To add another account, just drop
its CSV (same column format) into `data/raw/` with a descriptive filename.

## Notes

- `data/raw/*.csv` and `data/spend.db` are gitignored — this repo should never
  contain your actual transaction data, even though it's private.
- "Exclude transfers & card payments" is on by default in the sidebar since
  categories like `Transfer` and `Credit Card Payment` represent money moving
  between your own accounts, not discretionary spend.

## Features

What's actually built today, as distinct from the future-state plans below:

- CSV import with automatic dedup and in-place updates (see Usage above).
- Filtering by date range, account, category, and pending/posted status.
- Overview tab: total/income/net/avg-monthly metrics, spend over time, spend
  by category, top merchants, and category breakdown by month.
- Bills tab: recurring-transaction detection surfaces candidate bills
  (regular cadence + consistent amount) for confirmation, plus a manual bill
  registry (add/edit/delete, name/amount/category/cadence) with a
  monthly-equivalent total. See `src/spend_tracker/bills.py`.
- Budget Guideline tab: benchmark spend against a selectable framework
  (50/30/20, or category-specific ceilings for Housing/Transportation/Food/
  Savings), with editable per-bucket targets and concrete decrease guidance
  ($ and % over/under target) when a bucket is off track. See
  `src/spend_tracker/budget_guidelines.py`. An optional pay profile (gross
  pay, lumped pretax deductions, lumped taxes, per pay period, with an
  effective-date range) lets each bucket benchmark against the income basis
  (gross vs. net) it's traditionally expressed as, and counts
  payroll-deducted retirement/HSA/insurance contributions as real savings
  the bank data can't see; bank-deposit income alone remains the default
  when no pay profile is entered. See `src/spend_tracker/pay_profiles.py`.
- Household tab: tag each account with an owner (e.g. "You" vs "Partner"),
  independent of the bank/account label derived from the filename. Any
  newly-imported account not yet tagged prompts in the sidebar for who it
  belongs to (an existing owner or a new one); a "Manage account owners"
  editor lets you reassign anytime. Totals/Budget Guideline stay combined
  across all owners by default; this tab is the per-owner drill-down —
  per-owner spend/income/net, and grouped bar charts comparing owners
  side-by-side by category and by month. See `src/spend_tracker/owners.py`.
- Manual category overrides: fix an `Uncategorized` / `Category Pending`
  merchant's category once (Overview tab expander) and it applies to every
  past and future transaction with that exact description, surviving
  re-imports — stored separately from the imported data in a
  `category_overrides` table keyed by merchant pattern. See
  `src/spend_tracker/category_overrides.py`.
- Chat tab (read-only v1): ask questions about your transactions in a
  Streamlit chat backed by the `claude` CLI — e.g. "how much did I spend on
  Gas over $30?" or a conversational follow-up like "what about over $50
  instead?". Can only look and discuss, not write anything yet. See
  `src/spend_tracker/chat_advisor.py`, `chat_tools.py`, and `mcp_server.py`.
  If the CLI isn't installed or isn't signed in, the tab shows setup
  instructions (the exact install command, copyable) and a "check again"
  button instead of a raw error — `chat_advisor.check_setup()` detects this
  non-interactively via `claude auth status --json`.

## Possible next steps

- Support additional bank CSV formats (column-mapping config per source)

## Future state: benchmark spend against recommended budget guidelines

Compare actual spend, as a percentage of take-home income, against the general
allocation guidelines financial advisors commonly cite (e.g. the 50/30/20 rule —
50% needs, 30% wants, 20% savings/debt paydown — or more granular per-category
benchmarks like "housing ≤30% of income," "transportation ≤15%," "food ≤10–15%,"
"savings ≥20%"), and flag where actual spend is over or under.

**v1 shipped** (see Features above): selectable frameworks (50/30/20 and
category-specific ceilings), editable per-bucket targets, dollar/percent
decrease guidance when a bucket is off target, and each bucket's bar is now
split into a Bills segment (spend matching a registered bill's name) vs
Discretionary, so it's visible how much of any bucket is fixed vs
adjustable. A plain in-code category map remains a real gap.

**Income basis v1 shipped** (see Features above): an optional pay profile
(`src/spend_tracker/pay_profiles.py`, a `pay_profiles` table) records gross
pay, lumped pretax deductions (retirement + HSA/FSA + insurance), and
lumped taxes (federal/state/FICA) per pay period, over an effective-date
range rather than one row per paycheck. Each framework's `Framework`
dataclass now carries a per-bucket `income_basis` ("gross" or "net"), so
50/30/20 benchmarks against net throughout while category-specific ceilings
benchmark Housing/Transportation/Food against gross and Savings against
net — the actual income figure each guideline is traditionally expressed
against, rather than applying every bucket to the same net-deposits
figure. Payroll-deducted pretax amounts are added to the Savings bucket
(shown as a distinct "Payroll-deducted" bar segment alongside the bank's
own net) since that money never reaches the bank. Deliberately simplified:
pretax deductions and taxes are each a single lump number rather than
itemized, so a payroll-paid insurance premium is folded into "Savings"
alongside real retirement contributions — an accepted tradeoff for faster
data entry. Bank-deposit income remains the default when no pay profile is
entered; entering one is entirely optional.

Design notes for what's still unbuilt:

- **Category mapping**: each framework's category→bucket map lives in-code
  (`budget_guidelines.py`) rather than a config file, so remapping a category
  currently means editing Python, not the UI.

## Future state: multi-account household view with a per-person split

Track spend/income across multiple accounts that may belong to different
people (e.g. you and your spouse), so the overall household picture is
visible while still being able to see each person's spend separately, not
just a combined total. **This is about account ownership, not which bank
each account is at** — two accounts at the same bank should split by owner
just as easily as accounts at different banks; CSV-format compatibility is
a separate, orthogonal concern (see "additional bank CSV formats" above),
not a prerequisite for this feature.

**v1 shipped** (see Features above): an explicit `account_owners` table
(account -> owner) independent of the bank/account label
`account_name_from_filename` derives from the CSV filename, assigned via
an in-app prompt (not a filename convention or config file) — a
newly-imported account with no owner yet is flagged in the sidebar and
you pick an existing owner or type a new one, with a "Manage account
owners" editor for reassigning later. A Household tab has the real
side-by-side comparison (grouped bars per owner, by category and by
month) plus per-owner spend/income/net, while totals and the
budget-guideline benchmark stay combined across owners by default. See
`src/spend_tracker/owners.py`.

Design notes for what's still unbuilt:

- No bulk/multi-account assignment — each account is tagged one at a time
  in the sidebar prompt or the Household tab's manage-owners editor.
- The comparison charts default to the same date range and account
  filters as the rest of the app; there's no owner-specific date range
  (e.g. comparing this month for one owner against last month for the
  other).

## Future state: bills view with manual overrides

A dedicated view for recurring/fixed obligations (rent, utilities, insurance,
subscriptions, loan payments) — distinct from one-off discretionary spend —
with the ability to manually add or correct a bill if it isn't represented
correctly (miscategorized, paid through a channel that doesn't show up
clearly in the CSV, or missing entirely).

**v1 shipped** (see Features above): recurring-transaction detection
surfaces candidates for confirmation, and a manual bill registry supports
add, inline edit, and delete of name/amount/category/cadence, plus a
monthly-equivalent total. See `src/spend_tracker/bills.py`.

Still unbuilt:

- The bill registry (name/amount/category/cadence, and which bills exist at
  all) is still separate from the `category_overrides` mechanism (see
  Features above) that fixes a transaction's categorization — editing a
  bill doesn't reclassify its underlying transactions, and vice versa.

## Future state: in-app chat advisor for transaction classification, spend Q&A & affordability decisions

Rather than relying solely on hardcoded keyword rules, use Claude's judgment
to work through `Uncategorized` / `Category Pending` transactions and propose
correct categories — merchant description strings are often messy and
inconsistent in ways simple rules tend to miss, and fuzzy pattern matching is
exactly what Claude is good at.

This started as a plain Claude Code skill (a batch, run-from-the-terminal
workflow), but the more useful shape is a **back-and-forth chat interface
embedded in the app itself**, since some questions genuinely need a
conversation rather than a one-shot classification: e.g. the `Gas` category
in USAA exports mixes actual fuel purchases with snacks/drinks bought at the
same pump transaction, which a single batch pass can't disambiguate but a
chat can ("show me the Gas transactions over $30" vs "under $10").

The same chat surface is also the natural place for affordability
decisions — "based on my current financial state, can I afford a new
$X/month bill?" — since answering that well means combining several other
pieces already on this page (see the affordability bullet below) rather
than being a separate feature bolted on afterward.

Two design choices behind the backend, still true after shipping:

- **Wrap the Claude Code CLI, not the Anthropic API.** Calling the Messages
  API directly (or the Claude Agent SDK) requires a separate, metered API
  key billed per token. Shelling out to `claude -p "<prompt>" --output-format
  json` instead rides on an existing Claude Pro/Max subscription — same
  underlying model, no separate bill. This was a deliberate choice, not an
  oversight: the Agent SDK's `ClaudeSDKClient` *does* support a persistent
  in-process session (avoiding the per-message CLI startup latency,
  confirmed ~1-2s per call), but only under API-key/metered billing — there
  is no documented way to keep the CLI itself "warm" across turns. Accept
  the per-turn latency; revisit the Agent SDK only if that latency proves
  genuinely unacceptable in practice and paying for a separate API key
  becomes worth it.
- **Scoped custom tools via MCP, not generic Bash.** Claude Code's default
  Bash tool can touch anything in the repo, which is too broad for a chat
  embedded in a budgeting UI. Instead, a small local MCP server exposes
  typed tools and the CLI invocation is restricted to those — the
  CLI-equivalent of defining tools for the Messages API: same idea (typed
  schema, your code executes it, result goes back to Claude), just via the
  MCP protocol instead of inline in an API call.

**Read-only v1 shipped** (see Features above): a Chat tab (`src/spend_tracker/
app.py`) using `st.chat_message`/`st.chat_input` as planned. Confirms the
two design choices above in practice, with two corrections learned along
the way:

- The "deny Bash" mechanism is `--tools ""` (drops every built-in tool,
  Bash included) plus `--strict-mcp-config` (ignores any other MCP server
  configured on the machine) plus `--allowedTools` naming only
  `search_transactions` — not `settings.json`, which the design note above
  guessed at before checking the installed CLI's actual flags.
- `--continue` turned out to be unnecessary: each turn's JSON output
  already includes the session id, so the app always has it to pass to
  `--resume <session-id>` explicitly (kept in Streamlit `session_state`).
  Continuity is confirmed working, including a follow-up ("what about over
  $50 instead?") that correctly referenced the prior answer without it
  being restated.

The MCP server (`src/spend_tracker/mcp_server.py`, one fresh process per
turn via `claude`'s `--mcp-config`) exposes exactly one of the two planned
tools — `search_transactions` (filtering logic in `chat_tools.py`),
covering description substring/category/account/owner/status/date range/
signed amount, and returning a page of matching rows plus `matched_count`
and `total_amount` computed over *all* matches (not just the returned
page) so totals stay correct even when results are truncated. No
`apply_category_override` yet — that's deliberately deferred to a later
slice (see below); asked to recategorize a transaction, the chat correctly
declines and points at the Overview tab's manual override expander
instead.

Design notes for what's still unbuilt:

- **The write tool**, `apply_category_override` — wire it in now that the
  read-only version has been used a bit (see the "Confirmed
  classifications" bullet below for how it should write).
- **Affordability decisions ("can I afford a new $X/month bill?") depend on
  two other future-state pieces above — both now have a v1, which unblocks
  this, but it still needs the write tool and a third read tool below:**
  - The **bills view** (v1 shipped) to know current committed/fixed
    obligations separately from discretionary spend — "afford" should be
    judged against money left over *after* existing bills, not against total
    spend, which conflates the two.
  - The **budget-guideline benchmark** (v1 shipped) to phrase the answer in
    those terms — e.g. "adding this would push Needs to 54% of income, above
    the 50% target" — rather than just a raw dollar-leftover number.
  - A third read tool, `get_cashflow_summary(lookback_months)`, giving
    average income/bills/discretionary-spend/net over a trailing window
    (e.g. 6 months) rather than a single month, since spend is uneven month
    to month and a single recent month could make the answer misleadingly
    optimistic or pessimistic.
  - Answer format: state the trailing average net cash flow, subtract the
    new bill, and say what that does to slack and to any budget-guideline
    bucket — a concrete "here's the math," not a bare yes/no. Same framing
    caveat as the budget-guideline feature: this is arithmetic over logged
    history, not personalized financial advice, and the chat should say so.
- Confirmed classifications should be written into the existing
  `category_overrides` table (see Features above; already keyed by
  **merchant pattern**, not by individual transaction, so a fix applies to
  every past and future occurrence of that merchant and survives
  re-imports) via `db.set_category_override` — no new storage mechanism
  needed, just a new writer. The chat should show the proposed override and
  get an explicit confirm before writing, same as the manual override flow
  above.
- Complementary to, not a replacement for, the manual category override
  already shipped above — this is the assisted workflow for filling in that
  override table, rather than a separate mechanism from it.
