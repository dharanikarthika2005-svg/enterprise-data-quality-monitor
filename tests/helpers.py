"""Shared test helpers: build small, controlled CSV payloads."""
HEADER = "order_id,order_date,product_id,product_name,category,region,quantity,unit_price,customer_id"


def make_csv(rows: list[str], header: str = HEADER) -> bytes:
    return (header + "\n" + "\n".join(rows) + "\n").encode("utf-8")


def make_row(order_id="ORD-1001", date="2025-03-10", pid="PRD-101", name="Wireless Headphones",
             cat="Electronics", region="North", qty="2", price="79.99", cust="CUST-1001") -> str:
    return f"{order_id},{date},{pid},{name},{cat},{region},{qty},{price},{cust}"
