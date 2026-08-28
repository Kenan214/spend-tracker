"""Local Streamlit UI for visualizing spend over time.

Run with:
    streamlit run src/spend_tracker/app.py
"""
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import bills as bills_module
import budget_guidelines
import category_overrides as category_overrides_module
import chat_advisor as chat_advisor_module
import db
import importer
import owners as owners_module
import pay_profiles as pay_profiles_module

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


def escape_markdown_dollars(text: str) -> str:
    """Escape literal `$` so Streamlit's markdown renderer doesn't mistake a
    pair of dollar amounts (e.g. "over $30 ... totaling $2,873.46") for
    LaTeX math-mode delimiters.
    """
    return text.replace("$", r"\$")


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

    overrides_df = db.fetch_category_overrides(conn)
    tx = category_overrides_module.apply_overrides(tx, overrides_df)

    owners_df = db.fetch_account_owners(conn)
    tx = owners_module.with_owner(tx, owners_df)

    new_accounts = owners_module.unassigned_accounts(sorted(tx["account"].unique()), owners_df)
    if new_accounts:
        st.sidebar.header("New account owner")
        st.sidebar.caption("Who does this account belong to?")
        existing_owners = owners_module.known_owners(owners_df)
        for account in new_accounts:
            st.sidebar.markdown(f"**{account}**")
            choice_options = existing_owners + ["+ New owner"]
            choice = st.sidebar.selectbox(
                "Belongs to", choice_options, index=len(choice_options) - 1,
                key=f"owner_choice_{account}",
            )
            if choice == "+ New owner":
                owner_name = st.sidebar.text_input("New owner name", key=f"owner_name_{account}")
            else:
                owner_name = choice
            if st.sidebar.button("Save", key=f"owner_save_{account}") and owner_name:
                db.set_account_owner(conn, account, owner_name)
                st.rerun()

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

    pay_profiles_df = db.fetch_pay_profiles(conn)
    payroll_prorated = pay_profiles_module.prorated_totals(pay_profiles_df, start_date, end_date)
    payroll_savings = payroll_prorated["pretax_deductions"]
    # Gross-up actual bank-deposit net income by the payroll deductions a pay
    # profile says were withheld over this range, rather than trusting a
    # pay-stub-derived net figure that may not exactly match what hit the
    # bank (timing, rounding, non-payroll deposits). See pay_profiles.py.
    gross_income = total_income + payroll_prorated["pretax_deductions"] + payroll_prorated["taxes"]

    tab_overview, tab_bills, tab_budget, tab_household, tab_chat = st.tabs(
        ["Overview", "Bills", "Budget Guideline", "Household", "Chat"]
    )

    with tab_overview:
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Spend", f"${total_spend:,.2f}")
            col2.metric("Total Income", f"${total_income:,.2f}")
            col3.metric("Net", f"${net:,.2f}")
            col4.metric("Avg Monthly Spend", f"${avg_monthly_spend:,.2f}")

        if spend_only.empty:
            st.warning("No spend transactions match the current filters.")
        else:
            with st.container(border=True):
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

            with left, st.container(border=True):
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

            with right, st.container(border=True):
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

            with st.container(border=True):
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

            with st.expander("View transactions as table"):
                st.dataframe(
                    filtered[["tx_date", "description", "category", "amount", "status", "account", "owner"]]
                    .sort_values("tx_date", ascending=False),
                    use_container_width=True,
                )

            with st.expander("Manual category overrides"):
                st.caption(
                    "Fix a merchant's category once — it applies to every past and future "
                    "transaction with that exact description, and survives re-imports."
                )
                needs_category = sorted(
                    filtered.loc[
                        filtered["category"].isin(["Uncategorized", "Category Pending"]), "description"
                    ].unique()
                )
                if not needs_category:
                    st.caption("No Uncategorized / Category Pending transactions in the current filters.")
                else:
                    assignable_categories = sorted(
                        set(categories) - {"Uncategorized", "Category Pending"}
                    )
                    merchant = st.selectbox("Merchant description", needs_category, key="override_merchant")
                    new_category = st.selectbox(
                        "Assign category", assignable_categories, key="override_category"
                    )
                    if st.button("Save override", key="override_save") and new_category:
                        db.set_category_override(conn, merchant, new_category)
                        st.rerun()

                existing_overrides = db.fetch_category_overrides(conn)
                if not existing_overrides.empty:
                    st.markdown("**Active overrides**")
                    for _, row in existing_overrides.iterrows():
                        c1, c2, c3 = st.columns([4, 3, 1])
                        c1.write(row["merchant_pattern"])
                        c2.write(row["category"])
                        if c3.button("🗑", key=f"delete_override_{row['merchant_pattern']}"):
                            db.delete_category_override(conn, row["merchant_pattern"])
                            st.rerun()

    with tab_chat:
        with st.container(border=True):
            st.subheader("Chat advisor")
            st.caption(
                "Ask about your transactions — read-only for now (it can look and "
                "discuss, not make changes yet). Searches all imported transactions, "
                "not just what the sidebar filters currently show. Backed by the "
                "claude CLI, so it rides on your existing Claude subscription rather "
                "than a separately metered API key."
            )

        setup_status = st.session_state.get("chat_setup_status")
        if setup_status is None:
            setup_status = chat_advisor_module.check_setup()
            st.session_state["chat_setup_status"] = setup_status

        if not setup_status["installed"]:
            st.info(
                "The chat advisor needs the free **Claude Code CLI** installed — it's "
                "what lets this run on your existing Claude subscription instead of a "
                "separately billed API key. It isn't installed yet:"
            )
            st.markdown("**1.** Open **Terminal** (press ⌘+Space, type `Terminal`, press Return).")
            st.markdown("**2.** Paste this command and press Return:")
            st.code(chat_advisor_module.INSTALL_COMMAND, language="bash")
            st.markdown(
                "**3.** Once that finishes, run `claude` in the same Terminal window "
                "and sign in when your browser opens."
            )
            if st.button("I've installed it — check again", key="chat_setup_recheck"):
                st.session_state["chat_setup_status"] = None
                st.rerun()
        elif setup_status["logged_in"] is False:
            st.info(
                "Claude Code CLI is installed but not signed in yet. Open **Terminal**, "
                "run `claude`, and sign in when your browser opens — then come back here."
            )
            if st.button("I've signed in — check again", key="chat_setup_recheck"):
                st.session_state["chat_setup_status"] = None
                st.rerun()
        else:
            chat_messages = st.session_state.setdefault("chat_messages", [])
            st.session_state.setdefault("chat_session_id", None)

            for msg in chat_messages:
                with st.chat_message(msg["role"]):
                    st.markdown(escape_markdown_dollars(msg["content"]))

            if chat_messages and st.button("Clear conversation", key="chat_clear"):
                st.session_state["chat_messages"] = []
                st.session_state["chat_session_id"] = None
                st.rerun()

            user_prompt = st.chat_input("Ask about your transactions...")
            if user_prompt:
                chat_messages.append({"role": "user", "content": user_prompt})
                with st.chat_message("user"):
                    st.markdown(escape_markdown_dollars(user_prompt))
                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        try:
                            response = chat_advisor_module.send_message(
                                user_prompt, st.session_state["chat_session_id"]
                            )
                            st.session_state["chat_session_id"] = response["session_id"]
                            reply_text = response["text"]
                        except chat_advisor_module.ChatError as exc:
                            reply_text = f"⚠️ {exc}"
                    st.markdown(escape_markdown_dollars(reply_text))
                chat_messages.append({"role": "assistant", "content": reply_text})

    if spend_only.empty:
        return

    with tab_bills:
        with st.container(border=True):
            st.subheader("Bills")
            st.caption(
                "Recurring/fixed obligations, kept separate from one-off discretionary "
                "spend. Detected candidates are suggestions only — nothing is added "
                "until you confirm."
            )

            existing_bills = db.fetch_bills(conn)

            candidates = bills_module.detect_candidates(
                spend_only, known_names=set(existing_bills["name"]) if not existing_bills.empty else set()
            )
            st.markdown("**Detected recurring candidates**")
            if candidates.empty:
                st.caption("No recurring candidates found in the current filters.")
            else:
                for _, cand in candidates.iterrows():
                    c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 2, 2])
                    c1.write(cand["description"])
                    c2.write(cand["cadence"])
                    c3.write(f"${cand['avg_amount']:,.2f}")
                    c4.write(f"{cand['occurrences']}x seen")
                    if c5.button("Add as bill", key=f"add_candidate_{cand['description']}"):
                        db.add_bill(
                            conn,
                            name=cand["description"],
                            expected_amount=cand["avg_amount"],
                            category=cand["category"],
                            cadence=cand["cadence"],
                        )
                        st.rerun()

            st.markdown("**Your bills**")
            existing_bills = db.fetch_bills(conn)
            if existing_bills.empty:
                st.caption("No bills added yet.")
            else:
                monthly_total = sum(
                    bills_module.monthly_equivalent(row["expected_amount"], row["cadence"])
                    for _, row in existing_bills.iterrows()
                )
                st.metric("Total bills (monthly-equivalent)", f"${monthly_total:,.2f}")
                cadence_keys = list(bills_module.CADENCE_DAYS.keys())
                for _, bill in existing_bills.iterrows():
                    if st.session_state.get("editing_bill_id") == bill["id"]:
                        with st.form(f"edit_bill_form_{bill['id']}"):
                            e1, e2, e3, e4 = st.columns([3, 2, 2, 2])
                            edit_name = e1.text_input("Name", value=bill["name"])
                            edit_amount = e2.number_input(
                                "Amount ($)", min_value=0.0, step=1.0, value=float(bill["expected_amount"])
                            )
                            edit_category = e3.selectbox(
                                "Category", categories,
                                index=categories.index(bill["category"]) if bill["category"] in categories else 0,
                            )
                            edit_cadence = e4.selectbox(
                                "Cadence", cadence_keys, index=cadence_keys.index(bill["cadence"])
                            )
                            save_col, cancel_col = st.columns(2)
                            if save_col.form_submit_button("Save") and edit_name:
                                db.update_bill(
                                    conn, bill["id"], name=edit_name, expected_amount=edit_amount,
                                    category=edit_category, cadence=edit_cadence,
                                )
                                st.session_state["editing_bill_id"] = None
                                st.rerun()
                            if cancel_col.form_submit_button("Cancel"):
                                st.session_state["editing_bill_id"] = None
                                st.rerun()
                    else:
                        c1, c2, c3, c4, c5, c6 = st.columns([3, 2, 2, 2, 1, 1])
                        c1.write(bill["name"])
                        c2.write(bill["category"] or "—")
                        c3.write(bill["cadence"])
                        c4.write(f"${bill['expected_amount']:,.2f}")
                        if c5.button("✏️", key=f"edit_bill_{bill['id']}"):
                            st.session_state["editing_bill_id"] = bill["id"]
                            st.rerun()
                        if c6.button("🗑", key=f"delete_bill_{bill['id']}"):
                            db.delete_bill(conn, bill["id"])
                            st.rerun()

            with st.expander("Add a bill manually"):
                with st.form("add_bill_form", clear_on_submit=True):
                    name = st.text_input("Name")
                    expected_amount = st.number_input("Expected amount ($)", min_value=0.0, step=1.0)
                    category = st.selectbox("Category", categories)
                    cadence = st.selectbox("Cadence", list(bills_module.CADENCE_DAYS.keys()), index=2)
                    if st.form_submit_button("Add bill") and name:
                        db.add_bill(conn, name=name, expected_amount=expected_amount, category=category, cadence=cadence)
                        st.rerun()

    with tab_budget:
        with st.container(border=True):
            st.subheader("Budget guideline benchmark")
            st.caption(
                "General rules of thumb, not personalized financial advice. Income basis "
                "defaults to raw bank deposits; add a pay profile below for a precise "
                "gross/net split and to count payroll-deducted savings the bank never sees."
            )

            with st.expander("Pay profile (optional pay-stub detail)"):
                st.caption(
                    "Optional — bank-deposit income above is a sufficient default without "
                    "this. Entering gross pay and deductions per pay period lets "
                    "gross-based guidelines (e.g. \"housing ≤30% of income\") use actual "
                    "gross income instead of net, and counts 401(k)/HSA/insurance "
                    "contributions withheld before the paycheck hits the bank as real "
                    "savings. Pretax deductions (retirement + HSA/FSA + insurance) and "
                    "taxes (federal/state/FICA) are each entered as one lump sum, not "
                    "itemized — so payroll-paid insurance is folded into \"Savings\" "
                    "alongside retirement contributions. Use an effective-date range "
                    "rather than one row per paycheck; add a new row when pay or "
                    "deductions change (raise, open enrollment) instead of editing history."
                )

                if not pay_profiles_df.empty:
                    st.markdown("**Pay profiles**")
                    pay_frequency_keys = list(pay_profiles_module.PAY_FREQUENCIES.keys())
                    for _, profile in pay_profiles_df.iterrows():
                        if st.session_state.get("editing_pay_profile_id") == profile["id"]:
                            with st.form(f"edit_pay_profile_form_{profile['id']}"):
                                e1, e2, e3, e4 = st.columns(4)
                                edit_frequency = e1.selectbox(
                                    "Pay frequency", pay_frequency_keys,
                                    index=pay_frequency_keys.index(profile["pay_frequency"]),
                                )
                                edit_gross = e2.number_input(
                                    "Gross/period ($)", min_value=0.0, step=1.0,
                                    value=float(profile["gross_per_period"]),
                                )
                                edit_pretax = e3.number_input(
                                    "Pretax deductions/period ($)", min_value=0.0, step=1.0,
                                    value=float(profile["pretax_deductions_per_period"]),
                                )
                                edit_taxes = e4.number_input(
                                    "Taxes/period ($)", min_value=0.0, step=1.0,
                                    value=float(profile["taxes_per_period"]),
                                )
                                e5, e6 = st.columns(2)
                                edit_start = e5.date_input(
                                    "Effective start", value=profile["effective_start"].date()
                                )
                                edit_still_current = e6.checkbox(
                                    "Still in effect",
                                    value=pd.isna(profile["effective_end"]),
                                    key=f"edit_pay_profile_current_{profile['id']}",
                                )
                                edit_end = None
                                if not edit_still_current:
                                    default_end = (
                                        profile["effective_end"].date()
                                        if pd.notna(profile["effective_end"]) else edit_start
                                    )
                                    edit_end = st.date_input("Effective end", value=default_end)
                                save_col, cancel_col = st.columns(2)
                                if save_col.form_submit_button("Save"):
                                    db.update_pay_profile(
                                        conn, profile["id"], pay_frequency=edit_frequency,
                                        gross_per_period=edit_gross,
                                        pretax_deductions_per_period=edit_pretax,
                                        taxes_per_period=edit_taxes,
                                        effective_start=edit_start.isoformat(),
                                        effective_end=edit_end.isoformat() if edit_end else None,
                                    )
                                    st.session_state["editing_pay_profile_id"] = None
                                    st.rerun()
                                if cancel_col.form_submit_button("Cancel"):
                                    st.session_state["editing_pay_profile_id"] = None
                                    st.rerun()
                        else:
                            c1, c2, c3, c4, c5, c6, c7 = st.columns([2, 2, 2, 2, 2, 1, 1])
                            c1.write(profile["pay_frequency"])
                            c2.write(f"${profile['gross_per_period']:,.2f} gross")
                            c3.write(f"${pay_profiles_module.net_per_period(profile):,.2f} net")
                            end_label = (
                                profile["effective_end"].date().isoformat()
                                if pd.notna(profile["effective_end"]) else "current"
                            )
                            c4.write(f"{profile['effective_start'].date().isoformat()} –")
                            c5.write(end_label)
                            if c6.button("✏️", key=f"edit_pay_profile_{profile['id']}"):
                                st.session_state["editing_pay_profile_id"] = profile["id"]
                                st.rerun()
                            if c7.button("🗑", key=f"delete_pay_profile_{profile['id']}"):
                                db.delete_pay_profile(conn, profile["id"])
                                st.rerun()

                with st.form("add_pay_profile_form", clear_on_submit=True):
                    st.markdown("**Add a pay profile**")
                    f1, f2, f3, f4 = st.columns(4)
                    new_frequency = f1.selectbox(
                        "Pay frequency", list(pay_profiles_module.PAY_FREQUENCIES.keys())
                    )
                    new_gross = f2.number_input("Gross/period ($)", min_value=0.0, step=1.0)
                    new_pretax = f3.number_input(
                        "Pretax deductions/period ($)", min_value=0.0, step=1.0,
                        help="Retirement (401k/403b/IRA) + HSA/FSA + insurance premiums, combined.",
                    )
                    new_taxes = f4.number_input(
                        "Taxes/period ($)", min_value=0.0, step=1.0,
                        help="Federal + state + FICA withholding, combined.",
                    )
                    f5, f6 = st.columns(2)
                    new_start = f5.date_input("Effective start", value=min_date)
                    new_still_current = f6.checkbox("Still in effect", value=True)
                    new_end = None
                    if not new_still_current:
                        new_end = st.date_input("Effective end", value=max_date)
                    if st.form_submit_button("Add pay profile") and new_gross > 0:
                        db.add_pay_profile(
                            conn, pay_frequency=new_frequency, gross_per_period=new_gross,
                            pretax_deductions_per_period=new_pretax, taxes_per_period=new_taxes,
                            effective_start=new_start.isoformat(),
                            effective_end=new_end.isoformat() if new_end else None,
                        )
                        st.rerun()

            framework_keys = list(budget_guidelines.FRAMEWORKS.keys())
            framework_key = st.selectbox(
                "Framework",
                framework_keys,
                format_func=lambda k: budget_guidelines.FRAMEWORKS[k].name,
            )
            framework = budget_guidelines.FRAMEWORKS[framework_key]
            st.caption(f"**{framework.summary}**")
            with st.expander("Pros / cons of this framework"):
                st.markdown(f"**Pros:** {framework.pros}")
                st.markdown(f"**Cons:** {framework.cons}")

            if total_income <= 0:
                st.info("No income (deposits) in the current filters — can't compute percentages.")
            else:
                with st.expander("Edit targets (% of income)"):
                    targets = {}
                    for bucket in framework.bucket_order:
                        targets[bucket] = st.number_input(
                            f"{bucket} target %",
                            min_value=0.0, max_value=100.0,
                            value=framework.default_targets[bucket] * 100,
                            step=1.0,
                            key=f"target_{framework.key}_{bucket}",
                        ) / 100

                bill_names_lower = (
                    set(existing_bills["name"].str.lower()) if not existing_bills.empty else set()
                )

                income_denominator = {"net": total_income, "gross": gross_income}

                bucket_spend = {}
                segment_rows = []
                for bucket in framework.bucket_order:
                    if bucket == "Savings":
                        bucket_spend[bucket] = net + payroll_savings
                        segment_rows.append({"bucket": bucket, "segment": "Bank net", "amount": net})
                        if payroll_savings > 0:
                            segment_rows.append(
                                {"bucket": bucket, "segment": "Payroll-deducted", "amount": payroll_savings}
                            )
                    else:
                        bucket_df = spend_only[
                            spend_only["category"].map(lambda c: budget_guidelines.bucket_for(framework, c)) == bucket
                        ]
                        is_bill = bucket_df["description"].str.lower().isin(bill_names_lower)
                        bill_amount = bucket_df.loc[is_bill, "amount"].abs().sum()
                        discretionary_amount = bucket_df.loc[~is_bill, "amount"].abs().sum()
                        bucket_spend[bucket] = bill_amount + discretionary_amount
                        segment_rows.append({"bucket": bucket, "segment": "Bills", "amount": bill_amount})
                        segment_rows.append(
                            {"bucket": bucket, "segment": "Discretionary", "amount": discretionary_amount}
                        )
                segment_order = {"Bills": 0, "Discretionary": 1, "Bank net": 2, "Payroll-deducted": 3}
                segment_df = pd.DataFrame(segment_rows)
                segment_df["denom"] = segment_df["bucket"].map(framework.income_basis).map(income_denominator)
                segment_df["pct"] = segment_df["amount"] / segment_df["denom"]
                segment_df["segment_order"] = segment_df["segment"].map(segment_order)

                unmapped_spend = spend_only.loc[
                    spend_only["category"].map(lambda c: budget_guidelines.bucket_for(framework, c)) == "Unmapped",
                    "amount",
                ].abs().sum()

                guideline_df = pd.DataFrame([
                    {
                        "bucket": bucket,
                        "actual_pct": bucket_spend[bucket] / income_denominator[framework.income_basis[bucket]],
                        "target_pct": targets[bucket],
                        "direction": framework.direction[bucket],
                        "income_basis": framework.income_basis[bucket],
                    }
                    for bucket in framework.bucket_order
                ])
                guideline_df["off_target"] = guideline_df.apply(
                    lambda r: r["actual_pct"] < r["target_pct"] if r["direction"] == "min"
                    else r["actual_pct"] > r["target_pct"],
                    axis=1,
                )

                bucket_order = list(framework.bucket_order)
                y_scale = alt.Scale(paddingInner=0.4, paddingOuter=0.3)
                max_pct = max(guideline_df["actual_pct"].max(), guideline_df["target_pct"].max())
                x_scale = alt.Scale(domain=[0, max_pct * 1.2], nice=False)
                segment_domain = ["Bills", "Discretionary", "Bank net", "Payroll-deducted"]
                segment_range = [AQUA, BLUE, VIOLET, GREEN]
                bars = alt.Chart(segment_df).mark_bar(cornerRadiusEnd=4).encode(
                    x=alt.X("pct:Q", title="% of income", axis=alt.Axis(format="%"), scale=x_scale),
                    y=alt.Y("bucket:N", sort=bucket_order, title=None, scale=y_scale),
                    color=alt.Color(
                        "segment:N",
                        scale=alt.Scale(domain=segment_domain, range=segment_range),
                        legend=alt.Legend(title="Segment"),
                    ),
                    order=alt.Order("segment_order:Q"),
                    tooltip=[
                        alt.Tooltip("bucket:N", title="Bucket"),
                        alt.Tooltip("segment:N", title="Segment"),
                        alt.Tooltip("pct:Q", title="% of income", format=".1%"),
                    ],
                )
                ticks = alt.Chart(guideline_df).mark_tick(
                    color="#1a1a1a", thickness=3, size=28
                ).encode(
                    x=alt.X("target_pct:Q", scale=x_scale),
                    y=alt.Y("bucket:N", sort=bucket_order, title=None, scale=y_scale),
                )
                guideline_chart = (bars + ticks).properties(height=alt.Step(56))
                st.altair_chart(themed(guideline_chart), use_container_width=True)
                gross_buckets = [b for b in framework.bucket_order if framework.income_basis[b] == "gross"]
                net_buckets = [b for b in framework.bucket_order if framework.income_basis[b] == "net"]
                basis_note = (
                    f" {', '.join(gross_buckets)} benchmarked against gross income "
                    f"(\\${gross_income:,.2f}); {', '.join(net_buckets)} against net "
                    f"(\\${total_income:,.2f})."
                    if gross_buckets else ""
                )
                st.caption(
                    f"Bar = actual % of income, split into Bills (spend matching a registered "
                    f"bill's name) vs Discretionary · tick = target % under {framework.name}."
                    f"{basis_note} See the warnings below for which buckets are off target. "
                    "Manually-added bills whose name doesn't match a transaction description "
                    "aren't reflected in the Bills segment."
                )
                if payroll_savings > 0:
                    st.caption(
                        f"${payroll_savings:,.2f} of payroll-deducted retirement/HSA/insurance "
                        "contributions (from the pay profile above) are added to Savings, since "
                        "that money never reaches the bank."
                    )

                off_target = guideline_df[guideline_df["off_target"]]
                for _, row in off_target.iterrows():
                    bucket = row["bucket"]
                    denom = income_denominator[row["income_basis"]]
                    if row["direction"] == "max":
                        dollar_gap = bucket_spend[bucket] - row["target_pct"] * denom
                        pct_gap = (row["actual_pct"] - row["target_pct"]) * 100
                        st.warning(
                            f"**{bucket}**: ${dollar_gap:,.2f}/period over target — cut spend by "
                            f"about that much (~{pct_gap:.1f} pts) to hit the {row['target_pct']:.0%} target."
                        )
                    else:
                        dollar_gap = row["target_pct"] * denom - bucket_spend[bucket]
                        pct_gap = (row["target_pct"] - row["actual_pct"]) * 100
                        st.warning(
                            f"**{bucket}**: ${dollar_gap:,.2f}/period short of target — free up "
                            f"about that much (~{pct_gap:.1f} pts) to hit the {row['target_pct']:.0%} target."
                        )

                if unmapped_spend > 0:
                    mapped_buckets = ", ".join(b for b in framework.bucket_order if b != "Savings")
                    st.caption(
                        f"${unmapped_spend:,.2f} of spend is in categories not yet mapped to "
                        f"{mapped_buckets} (excluded from the bars above)."
                    )

    with tab_household:
        with st.container(border=True):
            st.subheader("Household")
            st.caption(
                "Totals above (and the budget-guideline benchmark) already combine "
                "every account by default. This tab breaks that down by owner for a "
                "side-by-side comparison."
            )

            with st.expander("Manage account owners"):
                all_accounts = sorted(tx["account"].unique())
                current_map = dict(zip(owners_df["account"], owners_df["owner"]))
                existing_owners = owners_module.known_owners(owners_df)
                for account in all_accounts:
                    current = current_map.get(account, owners_module.UNASSIGNED)
                    options = existing_owners + ["+ New owner"]
                    default_index = options.index(current) if current in options else len(options) - 1
                    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
                    c1.write(account)
                    choice = c2.selectbox(
                        "Owner", options, index=default_index,
                        key=f"manage_owner_choice_{account}", label_visibility="collapsed",
                    )
                    if choice == "+ New owner":
                        new_owner = c3.text_input(
                            "New owner", key=f"manage_owner_new_{account}",
                            label_visibility="collapsed", placeholder="New owner name",
                        )
                    else:
                        new_owner = choice
                    if c4.button("Save", key=f"manage_owner_save_{account}") and new_owner:
                        db.set_account_owner(conn, account, new_owner)
                        st.rerun()

            owner_spend = spend_only.groupby("owner", as_index=False)["amount"].sum()
            owner_spend["spend"] = owner_spend["amount"].abs()
            owner_income = (
                income_only.groupby("owner", as_index=False)["amount"].sum()
                .rename(columns={"amount": "income"})
            )
            owner_list = sorted(set(spend_only["owner"]) | set(income_only["owner"]))

            if len(owner_list) < 2:
                st.info(
                    "Only one owner is assigned across the accounts in the current "
                    "filters — assign a second owner above (e.g. a spouse's account) "
                    "to unlock the side-by-side comparison."
                )
            else:
                st.markdown("**Per-owner totals**")
                cols = st.columns(len(owner_list))
                for col, owner_name in zip(cols, owner_list):
                    o_spend = owner_spend.loc[owner_spend["owner"] == owner_name, "spend"].sum()
                    o_income = owner_income.loc[owner_income["owner"] == owner_name, "income"].sum()
                    with col.container(border=True):
                        st.markdown(f"**{owner_name}**")
                        st.metric("Spend", f"${o_spend:,.2f}")
                        st.metric("Income", f"${o_income:,.2f}")
                        st.metric("Net", f"${o_income - o_spend:,.2f}")

                owner_domain = owner_list
                owner_range = CATEGORY_PALETTE[: len(owner_domain)]

                st.markdown("**Spend by category, by owner**")
                top_cats = cat_totals.head(8)["category"].tolist()
                owner_cat = (
                    spend_only[spend_only["category"].isin(top_cats)]
                    .groupby(["category", "owner"], as_index=False)["amount"].sum()
                )
                owner_cat["spend"] = owner_cat["amount"].abs()
                cat_chart = alt.Chart(owner_cat).mark_bar(cornerRadiusEnd=4).encode(
                    x=alt.X("category:N", sort=top_cats, title=None),
                    xOffset=alt.XOffset("owner:N", sort=owner_domain),
                    y=alt.Y("spend:Q", title="Spend ($)"),
                    color=alt.Color(
                        "owner:N",
                        scale=alt.Scale(domain=owner_domain, range=owner_range),
                        legend=alt.Legend(title="Owner"),
                    ),
                    tooltip=[
                        alt.Tooltip("category:N", title="Category"),
                        alt.Tooltip("owner:N", title="Owner"),
                        alt.Tooltip("spend:Q", title="Spend", format="$,.2f"),
                    ],
                )
                st.altair_chart(themed(cat_chart), use_container_width=True)

                st.markdown("**Spend by month, by owner**")
                owner_month = (
                    spend_only.assign(month=spend_only["tx_date"].dt.to_period("M").dt.to_timestamp())
                    .groupby(["month", "owner"], as_index=False)["amount"].sum()
                )
                owner_month["spend"] = owner_month["amount"].abs()
                owner_month["month_label"] = owner_month["month"].dt.strftime("%b %Y")
                owner_month_order = (
                    owner_month[["month", "month_label"]]
                    .drop_duplicates().sort_values("month")["month_label"].tolist()
                )
                month_chart = alt.Chart(owner_month).mark_bar(cornerRadiusEnd=4).encode(
                    x=alt.X("month_label:O", sort=owner_month_order, title="Month"),
                    xOffset=alt.XOffset("owner:N", sort=owner_domain),
                    y=alt.Y("spend:Q", title="Spend ($)"),
                    color=alt.Color(
                        "owner:N",
                        scale=alt.Scale(domain=owner_domain, range=owner_range),
                        legend=alt.Legend(title="Owner"),
                    ),
                    tooltip=[
                        alt.Tooltip("month_label:N", title="Month"),
                        alt.Tooltip("owner:N", title="Owner"),
                        alt.Tooltip("spend:Q", title="Spend", format="$,.2f"),
                    ],
                )
                st.altair_chart(themed(month_chart), use_container_width=True)


if __name__ == "__main__":
    main()
