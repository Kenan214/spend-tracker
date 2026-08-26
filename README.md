# Spend Tracker

A local app + UI for visualizing personal spend over time, imported from bank/card
CSV exports. Everything runs and stores data locally — nothing leaves your machine.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

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

## Possible next steps

- Support additional bank CSV formats (column-mapping config per source)
- Manual category overrides for `Uncategorized` / `Category Pending` rows

## Future state: benchmark spend against recommended budget guidelines

Compare actual spend, as a percentage of take-home income, against the general
allocation guidelines financial advisors commonly cite (e.g. the 50/30/20 rule —
50% needs, 30% wants, 20% savings/debt paydown — or more granular per-category
benchmarks like "housing ≤30% of income," "transportation ≤15%," "food ≤10–15%,"
"savings ≥20%"), and flag where actual spend is over or under.

Design notes for when this gets built:

- **Income basis**: use the `Income`/`Paycheck` category totals already in the
  data as the take-home-pay figure — bank deposits are already net of tax and
  payroll deductions, so no separate manual income entry should be needed.
- **Category mapping**: USAA's ~50 categories are far more granular than a
  50/30/20-style framework, so this needs a config mapping granular categories
  to broader buckets (e.g. `Mortgage & Rent` → Housing; `Groceries` +
  `Restaurants` + `Fast Food` → Food; `Gas` + `Service & Parts` + `Parking` →
  Transportation; savings/investment transfers → Savings; everything else →
  Discretionary/Wants).
- **Configurable targets**: the specific recommended percentages vary by source
  and by the user's own goals, so targets should be editable (a config file or
  in-app settings), not hardcoded — ship one framework as a sensible default.
- **UI**: a new view showing actual % vs. target % per bucket (e.g. a bar or
  bullet chart per bucket, over/under called out), likely computed over the
  same date-range filter as the rest of the dashboard.
- **Framing**: these are general rules of thumb from personal finance sources,
  not personalized financial advice — the UI should say so.
