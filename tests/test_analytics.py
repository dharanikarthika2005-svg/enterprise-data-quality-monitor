import pandas as pd
import pytest

from src import analytics
from src.database import open_connection
from src.pipeline import process_file
from tests.helpers import make_csv, make_row


@pytest.fixture
def seeded(db_path):
    rows = [
        make_row(order_id="ORD-1001", date="2025-01-10", pid="PRD-101", cat="Electronics", region="North", qty="2", price="79.99"),
        make_row(order_id="ORD-1002", date="2025-01-20", pid="PRD-103", cat="Electronics", region="North", qty="1", price="24.50"),
        make_row(order_id="ORD-1003", date="2025-02-05", pid="PRD-201", cat="Home & Kitchen", region="South", qty="3", price="34.00"),
        make_row(order_id="ORD-1004", date="2025-02-06", pid="PRD-301", cat="Apparel", region="South", qty="-1", price="89.00"),
        make_row(order_id="ORD-1005", date="2025-02-07", pid="PRD-302", cat="Gadgets", region="South", qty="1", price="19.99"),
    ]
    process_file(make_csv(rows), "analytics.csv", db_path)
    return db_path


def test_empty_database_returns_empty_results(db_path):
    with open_connection(db_path) as conn:
        assert analytics.kpis(conn)["orders"] == 0
        assert analytics.kpis(conn)["aov"] is None
        assert analytics.monthly_revenue(conn).empty
        assert analytics.revenue_by_region(conn).empty
        assert analytics.date_bounds(conn) is None


def test_kpis_exclude_rejected_duplicate_and_flagged_records(seeded):
    with open_connection(seeded) as conn:
        k = analytics.kpis(conn)
    assert k["orders"] == 3                       # 1004 rejected, 1005 flagged and held back
    assert k["revenue"] == pytest.approx(286.48, abs=0.01)
    assert k["units"] == 6
    assert k["aov"] == pytest.approx(95.49, abs=0.01)


def test_monthly_growth_uses_previous_month(seeded):
    with open_connection(seeded) as conn:
        monthly = analytics.monthly_revenue(conn)
    assert list(monthly["month"]) == ["2025-01", "2025-02"]
    feb = monthly.iloc[1]
    assert feb["mom_growth_pct"] == pytest.approx(-44.71, abs=0.01)
    assert pd.isna(monthly.iloc[0]["yoy_growth_pct"])  # no January 2024 data, so YoY is unavailable


def test_regional_share_sums_to_100(seeded):
    with open_connection(seeded) as conn:
        by_region = analytics.revenue_by_region(conn)
    assert by_region["share_pct"].sum() == pytest.approx(100.0, abs=0.05)
    assert by_region.iloc[0]["region"] == "North"


def test_region_filter_is_applied_with_parameters(seeded):
    with open_connection(seeded) as conn:
        k = analytics.kpis(conn, region="South")
        none = analytics.kpis(conn, region="West")
    assert k["orders"] == 1 and k["revenue"] == pytest.approx(102.0)
    assert none["orders"] == 0


def test_date_filter_limits_results(seeded):
    with open_connection(seeded) as conn:
        k = analytics.kpis(conn, start_date="2025-02-01", end_date="2025-02-28")
    assert k["orders"] == 1


def test_top_products_respects_limit(seeded):
    with open_connection(seeded) as conn:
        top = analytics.top_products(conn, limit=1)
    assert len(top) == 1
    assert top.iloc[0]["product_id"] == "PRD-201"  # 3 units, the highest in the fixture
