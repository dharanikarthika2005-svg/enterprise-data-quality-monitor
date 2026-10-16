"""Business analytics: SQL over the accepted `sales` table only.
User-controlled values (dates, region, limit) are always passed as ? parameters, never formatted into SQL."""
import pandas as pd


def build_filters(start_date=None, end_date=None, region=None) -> tuple[str, list]:
    clauses, params = [], []
    if start_date:
        clauses.append("order_date >= ?")
        params.append(str(start_date))
    if end_date:
        clauses.append("order_date <= ?")
        params.append(str(end_date))
    if region and region != "All":
        clauses.append("region = ?")
        params.append(region)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def kpis(conn, start_date=None, end_date=None, region=None) -> dict:
    where, params = build_filters(start_date, end_date, region)
    row = conn.execute(
        f"""SELECT COUNT(*) AS orders, COALESCE(SUM(line_revenue), 0) AS revenue,
                   COALESCE(SUM(quantity), 0) AS units
            FROM sales{where}""",
        params,
    ).fetchone()
    orders, revenue = row["orders"], row["revenue"]
    return {
        "orders": orders,
        "revenue": revenue,
        "units": row["units"],
        # Average order value = total line revenue / number of accepted orders (one row per order_id).
        "aov": round(revenue / orders, 2) if orders else None,
    }


def monthly_revenue(conn, start_date=None, end_date=None, region=None) -> pd.DataFrame:
    """Monthly totals. MoM compares with the previous recorded month; YoY compares with the same month last year."""
    where, params = build_filters(start_date, end_date, region)
    return pd.read_sql_query(
        f"""WITH monthly AS (
                SELECT month, SUM(line_revenue) AS revenue, COUNT(*) AS orders, SUM(quantity) AS units
                FROM sales{where} GROUP BY month)
            SELECT m.month, m.revenue, m.orders, m.units,
                   ROUND(100.0 * (m.revenue - LAG(m.revenue) OVER (ORDER BY m.month))
                         / NULLIF(LAG(m.revenue) OVER (ORDER BY m.month), 0), 2) AS mom_growth_pct,
                   ROUND(100.0 * (m.revenue - p.revenue) / NULLIF(p.revenue, 0), 2) AS yoy_growth_pct
            FROM monthly m
            LEFT JOIN monthly p
                   ON p.month = printf('%04d-%s', CAST(substr(m.month, 1, 4) AS INTEGER) - 1, substr(m.month, 6, 2))
            ORDER BY m.month""",
        conn, params=params,
    )


def revenue_by_region(conn, start_date=None, end_date=None, region=None) -> pd.DataFrame:
    """A FROM-subquery gives per-region totals; a CROSS JOINed subquery gives the grand total for share %."""
    where, params = build_filters(start_date, end_date, region)
    return pd.read_sql_query(
        f"""SELECT r.region, r.revenue, r.orders, r.units,
                   ROUND(100.0 * r.revenue / NULLIF(t.total, 0), 2) AS share_pct
            FROM (SELECT region, SUM(line_revenue) AS revenue, COUNT(*) AS orders, SUM(quantity) AS units
                  FROM sales{where} GROUP BY region) r
            CROSS JOIN (SELECT COALESCE(SUM(line_revenue), 0) AS total FROM sales{where}) t
            ORDER BY r.revenue DESC""",
        conn, params=params + params,  # placeholders appear in both subqueries, in order
    )


def revenue_by_category(conn, start_date=None, end_date=None, region=None) -> pd.DataFrame:
    where, params = build_filters(start_date, end_date, region)
    return pd.read_sql_query(
        f"""SELECT category, SUM(line_revenue) AS revenue, COUNT(*) AS orders, SUM(quantity) AS units
            FROM sales{where} GROUP BY category ORDER BY revenue DESC""",
        conn, params=params,
    )


def top_products(conn, limit: int = 10, start_date=None, end_date=None, region=None) -> pd.DataFrame:
    where, params = build_filters(start_date, end_date, region)
    return pd.read_sql_query(
        f"""SELECT product_id, COALESCE(product_name, '(unnamed)') AS product_name, category,
                   SUM(quantity) AS units, SUM(line_revenue) AS revenue, COUNT(*) AS orders
            FROM sales{where}
            GROUP BY product_id, product_name, category
            ORDER BY units DESC, revenue DESC
            LIMIT ?""",
        conn, params=params + [int(limit)],
    )


def date_bounds(conn):
    row = conn.execute("SELECT MIN(order_date) AS lo, MAX(order_date) AS hi FROM sales").fetchone()
    return (row["lo"], row["hi"]) if row["lo"] else None


def list_regions(conn) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT region FROM sales ORDER BY region")]
