"""Page C: Data Quality. Scorecard, record summaries, error breakdown and downloadable error report."""
import plotly.express as px
import streamlit as st

from src.database import fetch_batch, fetch_batches, fetch_issue_rows, open_connection
from src.metrics import compute_quality_metrics, format_metric
from src.validation import RULES, build_error_report


def _label(row) -> str:
    return f"{row['batch_id']} · {row['file_name']} · {row['status']}"


def render() -> None:
    st.header("Data Quality")
    st.caption("Explains why records were rejected or flagged, and how reliable a batch is.")

    with open_connection() as conn:
        batches = fetch_batches(conn)
        if batches.empty:
            st.info("No batches yet. Process a file first.")
            return
        labels = [_label(r) for _, r in batches.iterrows()]
        selected = st.selectbox("Batch", labels, index=0)
        batch_id = batches.iloc[labels.index(selected)]["batch_id"]
        batch = fetch_batch(conn, batch_id)
        issues = fetch_issue_rows(conn, batch_id)

    if batch["status"] == "Failed":
        st.error(f"This batch failed: {batch['error_message']}")
        return

    metrics = compute_quality_metrics(batch)
    st.subheader("Quality scorecard")
    cols = st.columns(6)
    cols[0].metric("Validation pass rate", format_metric(metrics["validation_pass_rate"]))
    cols[1].metric("Rejected-record rate", format_metric(metrics["rejected_rate"]))
    cols[2].metric("Duplicate rate", format_metric(metrics["duplicate_rate"]))
    cols[3].metric("Missing-value rate", format_metric(metrics["missing_value_rate"]))
    cols[4].metric("Invalid-value rate", format_metric(metrics["invalid_value_rate"]))
    cols[5].metric("Processing time", format_metric(metrics["duration_seconds"], " s"))
    with st.expander("How each metric is calculated"):
        st.markdown(
            "- **Validation pass rate** = (accepted + flagged) ÷ records received × 100\n"
            "- **Rejected-record rate** = rejected ÷ records received × 100\n"
            "- **Duplicate rate** = duplicates ÷ records received × 100\n"
            "- **Missing-value rate** = blank mandatory fields ÷ mandatory-field checks × 100\n"
            "- **Invalid-value rate** = failed format/type checks ÷ populated-field checks × 100"
        )

    st.subheader("Record summary")
    cols = st.columns(5)
    cols[0].metric("Received", f"{batch['total_received']:,}")
    cols[1].metric("Accepted", f"{batch['accepted_count']:,}")
    cols[2].metric("Flagged (held for review)", f"{batch['flagged_count']:,}")
    cols[3].metric("Rejected", f"{batch['rejected_count']:,}")
    cols[4].metric("Duplicates", f"{batch['duplicate_count']:,}")
    st.caption(f"Malformed lines skipped during parsing: {batch['malformed_lines']:,}")

    issue_only = issues[issues["rule_id"].notna()]
    if issue_only.empty:
        st.success("No validation issues were found in this batch.")
    else:
        breakdown = (
            issue_only.groupby(["rule_id", "severity"]).size().reset_index(name="count")
        )
        breakdown["rule"] = breakdown["rule_id"].map(lambda r: f"{r} · {RULES[r].title}")
        breakdown["category"] = breakdown["rule_id"].map(lambda r: RULES[r].category)
        st.subheader("Error breakdown by validation rule")
        fig = px.bar(breakdown, x="count", y="rule", color="severity", orientation="h",
                     color_discrete_map={"reject": "#C0392B", "flag": "#E67E22"},
                     hover_data=["category"], title="Issues per rule")
        fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Rule catalogue (stable IDs, severity and trigger condition)"):
            catalogue = [{"Rule": r.rule_id, "Category": r.category, "Severity": r.severity,
                          "Title": r.title, "Condition": r.condition} for r in RULES.values()]
            st.dataframe(catalogue, use_container_width=True, hide_index=True)

        st.subheader("Filterable validation details")
        f1, f2, f3 = st.columns([2, 2, 1])
        rule_filter = f1.multiselect("Rule", sorted(issue_only["rule_id"].unique()))
        status_filter = f2.multiselect("Record status", ["rejected", "duplicate", "flagged"])
        search = f3.text_input("Order ID contains")
        view = issue_only.copy()
        if rule_filter:
            view = view[view["rule_id"].isin(rule_filter)]
        if status_filter:
            view = view[view["status"].isin(status_filter)]
        if search:
            view = view[view["order_id"].fillna("").str.contains(search, case=False)]
        st.caption(f"{len(view):,} matching issue(s)")
        st.dataframe(view[["row_number", "order_id", "status", "rule_id", "severity", "message"]],
                     use_container_width=True, hide_index=True)

    report = build_error_report(issues)
    st.download_button(
        "Download error report (CSV)",
        data=report.to_csv(index=False).encode("utf-8"),
        file_name=f"{batch_id}_error_report.csv",
        mime="text/csv",
        disabled=report.empty,
        help="Rejected, duplicate and flagged records with rule IDs, messages and original values.",
    )
