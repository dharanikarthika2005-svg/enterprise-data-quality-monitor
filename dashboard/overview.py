"""Page A: Overview. KPI cards, latest batch, overall quality, recent alerts and activity."""
import streamlit as st

from dashboard.common import money
from src.analytics import kpis
from src.database import count_sales, fetch_batches, open_connection
from src.monitoring import all_alerts, batch_summary_table, overall_quality
from src.metrics import format_metric


def render() -> None:
    st.header("Overview")
    st.caption("Business results from accepted sales, and how far those results can be trusted.")

    with open_connection() as conn:
        figures = kpis(conn)
        batches = fetch_batches(conn)
        loaded_total = count_sales(conn)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total revenue", money(figures["revenue"]))
    c2.metric("Accepted orders", f"{figures['orders']:,}")
    c3.metric("Units sold", f"{figures['units']:,}")
    c4.metric("Average order value", money(figures["aov"]))

    if batches.empty:
        st.info("No batches have been processed yet. Open 'Upload & Process' to load your first file.")
        return

    latest = batches.iloc[0]
    alerts = all_alerts(batches)
    failed = int((batches["status"] == "Failed").sum())
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Latest batch", latest["status"], help=f"{latest['batch_id']} · {latest['file_name']}")
    q2.metric("Overall data-quality pass rate", format_metric(overall_quality(batches)))
    q3.metric("Batches processed", f"{len(batches):,}", help=f"{failed} failed")
    q4.metric("Active alerts", f"{len(alerts):,}")

    st.subheader("Recent alerts")
    if not alerts:
        st.success("No threshold alerts across completed batches.")
    for alert in alerts[:5]:
        st.warning(f"**{alert.label}** = {alert.actual:.2f}{'s' if alert.metric == 'duration_seconds' else '%'} "
                   f"(threshold {alert.threshold:g}). {alert.explanation}  \n"
                   f"*Recommended step:* {alert.recommendation}")

    st.subheader("Recent batch activity")
    st.dataframe(batch_summary_table(batches.head(5)), use_container_width=True, hide_index=True)
    if loaded_total == 0:
        st.caption("Sales analytics will appear here once accepted records are loaded.")
