"""Page E: Sales Analytics. SQL-driven charts and tables with date and region filters."""
from datetime import date

import streamlit as st

from dashboard.common import bar_chart, empty_state, line_chart, money
from src import analytics as sql
from src.database import count_sales, open_connection


def render() -> None:
    st.header("Sales Analytics")
    st.caption("Accepted sales only. Rejected, duplicate and held-for-review records are excluded.")

    with open_connection() as conn:
        if count_sales(conn) == 0:
            empty_state("No accepted sales yet. Process a file on 'Upload & Process' to see analytics.")
            return
        lo, hi = sql.date_bounds(conn)
        regions = ["All"] + sql.list_regions(conn)

        f1, f2, f3 = st.columns([1, 1, 1])
        start = f1.date_input("From", value=date.fromisoformat(lo), min_value=date.fromisoformat(lo),
                              max_value=date.fromisoformat(hi))
        end = f2.date_input("To", value=date.fromisoformat(hi), min_value=date.fromisoformat(lo),
                            max_value=date.fromisoformat(hi))
        region = f3.selectbox("Region", regions)
        if start > end:
            st.error("'From' must be on or before 'To'.")
            return

        filters = dict(start_date=start, end_date=end, region=region)
        figures = sql.kpis(conn, **filters)
        monthly = sql.monthly_revenue(conn, **filters)
        by_region = sql.revenue_by_region(conn, **filters)
        by_category = sql.revenue_by_category(conn, **filters)
        products = sql.top_products(conn, limit=10, **filters)

    if figures["orders"] == 0:
        empty_state("No accepted sales match these filters.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Revenue", money(figures["revenue"]))
    c2.metric("Orders", f"{figures['orders']:,}")
    c3.metric("Units", f"{figures['units']:,}")
    c4.metric("Average order value", money(figures["aov"]))

    st.plotly_chart(line_chart(monthly, "month", "revenue", "Monthly revenue", "Revenue"),
                    use_container_width=True)
    st.subheader("Month-over-month and year-over-year growth")
    if len(monthly) < 2:
        st.info("Growth needs at least two months of data.")
    growth = monthly[["month", "revenue", "mom_growth_pct", "yoy_growth_pct"]].rename(columns={
        "mom_growth_pct": "MoM growth %", "yoy_growth_pct": "YoY growth %"})
    st.dataframe(growth, use_container_width=True, hide_index=True)

    left, right = st.columns(2)
    left.plotly_chart(bar_chart(by_region, "region", "revenue", "Revenue by region"), use_container_width=True)
    right.plotly_chart(bar_chart(by_category, "category", "revenue", "Revenue by category"),
                       use_container_width=True)

    st.subheader("Regional performance")
    st.dataframe(by_region, use_container_width=True, hide_index=True)
    st.subheader("Top products by units sold")
    st.dataframe(products, use_container_width=True, hide_index=True)
