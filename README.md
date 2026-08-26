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

1. Run the app:
   ```bash
   streamlit run src/spend_tracker/app.py
   ```
2. Import a CSV export either by dragging it onto the uploader in the sidebar,
   or by dropping the file into `data/raw/` directly — both land in the same
   place and get imported into a local SQLite database (`data/spend.db`).
3. Filter by date range, account, category, and pending/posted status.

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
- Budget vs. actual comparison per category
