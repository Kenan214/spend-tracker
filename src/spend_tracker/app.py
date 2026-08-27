"""Local Streamlit UI for visualizing spend over time.

Run with:
    streamlit run src/spend_tracker/app.py
"""
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import budget_guidelines
import db
import importer

# --- palette (dataviz skill reference palette — fixed hue order) ---
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7",
)
CATEGORY_PALETTE = [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET]
OTHER_GRAY = "#898781"
GRID_COLOR = "#e1e0d9"
AXIS_COLOR = "#c3c2b7"
LABEL_COLOR = "#52514e"
SURFACE = "#fcfcfb"

TRANSFER_LIKE_CATEGORIES = {"Transfer", "Credit Card Payment", "Financial"}

RAW_DIR = db.PROJECT_ROOT / "data" / "raw"


def themed(chart: alt.Chart) -> alt.Chart:
    return (
        chart.configure_view(strokeWidth=0, fill=SURFACE)
        .configure_axis(
            domainColor=AXIS_COLOR,
            gridColor=GRID_COLOR,
            labelColor=LABEL_COLOR,
            titleColor=LABEL_COLOR,
            tickColor=AXIS_COLOR,
        )
        .configure_legend(labelColor=LABEL_COLOR, titleColor=LABEL_COLOR)
    )


def save_uploaded_files(uploaded_files) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for uploaded in uploaded_files:
        dest = RAW_DIR / uploaded.name
        dest.write_bytes(uploaded.getvalue())


def import_new_files(conn) -> None:
    files = importer.find_csv_files(RAW_DIR)
    if not files:
        return
    total_inserted = total_updated = 0
    errors = []
    for path in files:
        try:
            df = importer.load_csv(path)
        except (ValueError, pd.errors.ParserError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        inserted, updated = db.upsert_transactions(conn, df)
        total_inserted += inserted
        total_updated += updated
    if total_inserted or total_updated:
        st.sidebar.success(f"Imported: {total_inserted} new, {total_updated} updated")
    for err in errors:
        st.sidebar.error(f"Skipped {err}")


def main() -> None:
    st.set_page_config(page_title="Spend Tracker", layout="wide")
    st.title("Spend Tracker")

    st.sidebar.header("Import")
    uploaded_files = st.sidebar.file_uploader(
        "Drag & drop a CSV export",
        type="csv",
        accept_multiple_files=True,
        help="USAA-style export: Date, Description, Original Description, Category, Amount, Status",
    )
    if uploaded_files:
        save_uploaded_files(uploaded_files)

    conn = db.get_connection()
    import_new_files(conn)
    tx = db.fetch_transactions(conn)

    if tx.empty:
        st.info("Drag a CSV export into the uploader in the sidebar to get started.")
        return

    st.sidebar.header("Filters")

    min_date, max_date = tx["tx_date"].min().date(), tx["tx_date"].max().date()
    date_range = st.sidebar.date_input(
        "Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date
    )
    if not isinstance(date_range, tuple) or len(date_range) != 2:
        st.stop()
    start_date, end_date = date_range

    accounts = sorted(tx["account"].unique())
    selected_accounts = st.sidebar.multiselect("Accounts", accounts, default=accounts)

    include_pending = st.sidebar.checkbox("Include pending transactions", value=False)
    exclude_transfers = st.sidebar.checkbox(
        "Exclude transfers & card payments", value=True,
        help="Hides Transfer, Credit Card Payment, and Financial categories, which "
             "represent money moving between your own accounts rather than spend.",
    )

    categories = sorted(tx["category"].unique())
    selected_categories = st.sidebar.multiselect("Categories", categories, default=categories)

    mask = (
        (tx["tx_date"].dt.date >= start_date)
        & (tx["tx_date"].dt.date <= end_date)
        & (tx["account"].isin(selected_accounts))
        & (tx["category"].isin(selected_categories))
    )
    if not include_pending:
        mask &= tx["status"] == "Posted"
    filtered = tx[mask].copy()

    if exclude_transfers:
        spend_df = filtered[~filtered["category"].isin(TRANSFER_LIKE_CATEGORIES)].copy()
    else:
        spend_df = filtered

    spend_only = spend_df[spend_df["amount"] < 0]
    income_only = filtered[filtered["amount"] > 0]

    total_spend = spend_only["amount"].abs().sum()
    total_income = income_only["amount"].sum()
    net = total_income - total_spend
    n_months = max(spend_only["tx_date"].dt.to_period("M").nunique(), 1)
    avg_monthly_spend = total_spend / n_months

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Spend", f"${total_spend:,.2f}")
    col2.metric("Total Income", f"${total_income:,.2f}")
    col3.metric("Net", f"${net:,.2f}")
    col4.metric("Avg Monthly Spend", f"${avg_monthly_spend:,.2f}")

    if spend_only.empty:
        st.warning("No spend transactions match the current filters.")
        return

    st.subheader("Spend over time")
    monthly = (
        spend_only.assign(month=spend_only["tx_date"].dt.to_period("M").dt.to_timestamp())
        .groupby("month", as_index=False)["amount"].sum()
        .sort_values("month")
    )
    monthly["spend"] = monthly["amount"].abs()
    monthly["month_label"] = monthly["month"].dt.strftime("%b %Y")
    month_order = monthly["month_label"].tolist()
    time_chart = alt.Chart(monthly).mark_bar(cornerRadiusEnd=4, size=18, color=BLUE).encode(
        x=alt.X("month_label:O", title="Month", sort=month_order),
        y=alt.Y("spend:Q", title="Spend ($)"),
        tooltip=[
            alt.Tooltip("month_label:N", title="Month"),
            alt.Tooltip("spend:Q", title="Spend", format="$,.2f"),
        ],
    )
    st.altair_chart(themed(time_chart), use_container_width=True)

    cat_totals = spend_only.groupby("category", as_index=False)["amount"].sum()
    cat_totals["spend"] = cat_totals["amount"].abs()
    cat_totals = cat_totals.sort_values("spend", ascending=False)

    left, right = st.columns(2)

    with left:
        st.subheader("Spend by category")
        top = cat_totals.head(8)[["category", "spend"]].copy()
        rest = cat_totals.iloc[8:]
        if len(rest):
            other_row = pd.DataFrame([{"category": "Other", "spend": rest["spend"].sum()}])
            top = pd.concat([top, other_row], ignore_index=True)
        bars = alt.Chart(top).mark_bar(cornerRadiusEnd=4, color=BLUE).encode(
            x=alt.X("spend:Q", title="Spend ($)"),
            y=alt.Y("category:N", sort="-x", title=None),
            tooltip=[alt.Tooltip("category:N", title="Category"), alt.Tooltip("spend:Q", format="$,.2f")],
        )
        labels = bars.mark_text(align="left", dx=4, color=LABEL_COLOR).encode(
            text=alt.Text("spend:Q", format="$,.0f")
        )
        st.altair_chart(themed(bars + labels), use_container_width=True)

    with right:
        st.subheader("Top merchants")
        merchant = spend_only.groupby("description", as_index=False)["amount"].sum()
        merchant["spend"] = merchant["amount"].abs()
        merchant = merchant.sort_values("spend", ascending=False).head(10)
        m_bars = alt.Chart(merchant).mark_bar(cornerRadiusEnd=4, color=BLUE).encode(
            x=alt.X("spend:Q", title="Spend ($)"),
            y=alt.Y("description:N", sort="-x", title=None),
            tooltip=[alt.Tooltip("description:N", title="Merchant"), alt.Tooltip("spend:Q", format="$,.2f")],
        )
        st.altair_chart(themed(m_bars), use_container_width=True)

    st.subheader("Category breakdown by month")
    top7_names = cat_totals.head(7)["category"].tolist()
    monthly_cat = spend_only.assign(
        month=spend_only["tx_date"].dt.to_period("M").dt.to_timestamp(),
        bucket=spend_only["category"].map(lambda c: c if c in top7_names else "Other"),
    )
    monthly_cat = monthly_cat.groupby(["month", "bucket"], as_index=False)["amount"].sum()
    monthly_cat["spend"] = monthly_cat["amount"].abs()
    monthly_cat["month_label"] = monthly_cat["month"].dt.strftime("%b %Y")
    stack_month_order = (
        monthly_cat[["month", "month_label"]].drop_duplicates().sort_values("month")["month_label"].tolist()
    )

    domain = list(top7_names)
    color_range = CATEGORY_PALETTE[: len(top7_names)]
    if "Other" in monthly_cat["bucket"].unique():
        domain.append("Other")
        color_range.append(OTHER_GRAY)

    stacked = alt.Chart(monthly_cat).mark_bar(stroke=SURFACE, strokeWidth=1).encode(
        x=alt.X("month_label:O", title="Month", sort=stack_month_order),
        y=alt.Y("spend:Q", title="Spend ($)", stack="zero"),
        color=alt.Color(
            "bucket:N",
            scale=alt.Scale(domain=domain, range=color_range),
            legend=alt.Legend(title="Category"),
        ),
        order=alt.Order("spend:Q", sort="descending"),
        tooltip=[
            alt.Tooltip("month_label:N", title="Month"),
            alt.Tooltip("bucket:N", title="Category"),
            alt.Tooltip("spend:Q", title="Spend", format="$,.2f"),
        ],
    )
    st.altair_chart(themed(stacked), use_container_width=True)

    st.subheader("Budget guideline: 50/30/20")
    st.caption(
        "General rule of thumb, not personalized financial advice. Income basis "
        "is raw bank deposits (no pay-stub entry yet), so payroll-deducted "
        "savings/insurance aren't reflected here."
    )
    if total_income <= 0:
        st.info("No income (deposits) in the current filters — can't compute percentages.")
    else:
        needs_spend = spend_only.loc[
            spend_only["category"].map(budget_guidelines.bucket_for) == "Needs", "amount"
        ].abs().sum()
        wants_spend = spend_only.loc[
            spend_only["category"].map(budget_guidelines.bucket_for) == "Wants", "amount"
        ].abs().sum()
        unmapped_spend = spend_only.loc[
            spend_only["category"].map(budget_guidelines.bucket_for) == "Unmapped", "amount"
        ].abs().sum()

        guideline_df = pd.DataFrame([
            {"bucket": "Needs", "actual_pct": needs_spend / total_income,
             "target_pct": budget_guidelines.TARGET_PCT["Needs"]},
            {"bucket": "Wants", "actual_pct": wants_spend / total_income,
             "target_pct": budget_guidelines.TARGET_PCT["Wants"]},
            {"bucket": "Savings", "actual_pct": net / total_income,
             "target_pct": budget_guidelines.TARGET_PCT["Savings"]},
        ])
        guideline_df["over_target"] = guideline_df.apply(
            lambda r: r["actual_pct"] < r["target_pct"] if r["bucket"] == "Savings"
            else r["actual_pct"] > r["target_pct"],
            axis=1,
        )

        bucket_order = ["Needs", "Wants", "Savings"]
        bars = alt.Chart(guideline_df).mark_bar(cornerRadiusEnd=4, size=24).encode(
            x=alt.X("actual_pct:Q", title="% of income", axis=alt.Axis(format="%")),
            y=alt.Y("bucket:N", sort=bucket_order, title=None),
            color=alt.condition(
                "datum.over_target", alt.value(ORANGE), alt.value(BLUE)
            ),
            tooltip=[
                alt.Tooltip("bucket:N", title="Bucket"),
                alt.Tooltip("actual_pct:Q", title="Actual", format=".1%"),
                alt.Tooltip("target_pct:Q", title="Target", format=".1%"),
            ],
        )
        ticks = alt.Chart(guideline_df).mark_tick(
            color=LABEL_COLOR, thickness=2, size=32
        ).encode(
            x="target_pct:Q",
            y=alt.Y("bucket:N", sort=bucket_order, title=None),
        )
        st.altair_chart(themed(bars + ticks), use_container_width=True)
        st.caption("Bar = actual % of income · tick = target % under 50/30/20. Orange = off target.")

        if unmapped_spend > 0:
            st.caption(
                f"${unmapped_spend:,.2f} of spend is in categories not yet mapped to "
                "Needs/Wants (excluded from the bars above)."
            )

    with st.expander("View transactions as table"):
        st.dataframe(
            filtered[["tx_date", "description", "category", "amount", "status", "account"]]
            .sort_values("tx_date", ascending=False),
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
