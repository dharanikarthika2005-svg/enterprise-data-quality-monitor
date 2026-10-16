"""Page D: Batch History. Audit list, batch detail, two-batch comparison, trends and file-import log."""
import streamlit as st

from dashboard.common import line_chart
from src.database import fetch_batch, fetch_batches, fetch_file_imports, open_connection
from src.metrics import compute_quality_metrics, format_metric
from src.monitoring import (
    METRIC_LABELS, all_alerts, batch_summary_table, build_trend_frame, compare_batches,
)


def render() -> None:
    st.header("Batch History")
    st.caption("Every import is kept. Earlier batches are never overwritten.")

    with open_connection() as conn:
        batches = fetch_batches(conn)
        imports = fetch_file_imports(conn)

    if batches.empty:
        st.info("No batches yet. Process a file to start the audit trail.")
        return

    st.subheader("All batches")
    st.dataframe(batch_summary_table(batches), use_container_width=True, hide_index=True)

    labels = {f"{r['batch_id']} · {r['file_name']} · {r['status']}": r["batch_id"]
              for _, r in batches.iterrows()}
    option_labels = list(labels)

    st.subheader("Batch detail")
    chosen = st.selectbox("Select a batch", option_labels, key="detail_batch")
    with open_connection() as conn:
        detail = fetch_batch(conn, labels[chosen])
    d = compute_quality_metrics(detail)
    cols = st.columns(4)
    cols[0].metric("Status", detail["status"])
    cols[1].metric("Submitted (UTC)", detail["submitted_at"])
    cols[2].metric("Duration", format_metric(d["duration_seconds"], " s"))
    cols[3].metric("Loaded to sales", f"{detail['loaded_count']:,}")
    st.write(f"**Checksum (SHA-256):** `{detail['checksum_sha256']}`")
    if detail["error_message"]:
        st.error(detail["error_message"])

    st.subheader("Compare two batches")
    if len(option_labels) < 2:
        st.info("Process at least two batches to compare their quality.")
    else:
        c1, c2 = st.columns(2)
        first = c1.selectbox("Batch A (baseline)", option_labels, index=1, key="cmp_a")
        second = c2.selectbox("Batch B (new)", option_labels, index=0, key="cmp_b")
        with open_connection() as conn:
            a = fetch_batch(conn, labels[first])
            b = fetch_batch(conn, labels[second])
        if labels[first] == labels[second]:
            st.info("Choose two different batches to compare.")
        else:
            comparison = compare_batches(a, b)
            st.dataframe(comparison, use_container_width=True, hide_index=True)
            improved = (comparison["Verdict"] == "Improved").sum()
            worse = (comparison["Verdict"] == "Deteriorated").sum()
            st.caption(f"Batch B vs Batch A: {improved} metric(s) improved, {worse} deteriorated.")

    st.subheader("Cross-batch quality trends")
    trend = build_trend_frame(batches)
    if trend.empty or len(trend) < 2:
        st.info("Trend charts need at least two completed batches.")
    else:
        trend_cols = st.columns(2)
        charts = [
            ("validation_pass_rate", "Validation pass rate (%)"),
            ("rejected_rate", "Rejected-record rate (%)"),
            ("missing_value_rate", "Missing-value rate (%)"),
            ("duplicate_rate", "Duplicate rate (%)"),
            ("duration_seconds", "Processing duration (s)"),
        ]
        for i, (metric, title) in enumerate(charts):
            fig = line_chart(trend, "submitted_at", metric, title=title, y_label=METRIC_LABELS[metric])
            trend_cols[i % 2].plotly_chart(fig, use_container_width=True)

    st.subheader("Threshold alerts")
    alerts = all_alerts(batches)
    if not alerts:
        st.success("No thresholds have been breached.")
    for alert in alerts:
        st.warning(f"**{alert.batch_id}** · {alert.explanation}  \n*Recommended step:* {alert.recommendation}")

    st.subheader("File import log")
    st.caption("Includes files blocked as duplicates. Blocked attempts do not create batches.")
    st.dataframe(imports, use_container_width=True, hide_index=True)
