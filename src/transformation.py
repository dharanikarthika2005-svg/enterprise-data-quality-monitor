"""Transform helpers: column standardisation, string cleaning and derived sales fields."""
import pandas as pd


def standardise_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """'Order Date' becomes 'order_date'. Values are not changed."""
    frame = frame.copy()
    frame.columns = [
        str(c).strip().lower().replace(" ", "_").replace("-", "_") for c in frame.columns
    ]
    return frame


def clean_string_values(frame: pd.DataFrame) -> pd.DataFrame:
    """Replace missing cells with blanks and trim whitespace. Values stay as text at this stage."""
    return frame.fillna("").apply(lambda col: col.astype(str).str.strip())


def build_sales_row(clean: dict, batch_id: str, loaded_at: str) -> dict:
    """Derive warehouse fields for one accepted record (line revenue, month)."""
    order_date = clean["order_date"]
    quantity = clean["quantity"]
    unit_price = clean["unit_price"]
    return {
        "order_id": clean["order_id"],
        "order_date": order_date.isoformat(),
        "month": order_date.strftime("%Y-%m"),
        "product_id": clean["product_id"],
        "product_name": clean["product_name"] or None,
        "category": clean["category"],
        "region": clean["region"],
        "quantity": quantity,
        "unit_price": unit_price,
        "line_revenue": round(quantity * unit_price, 2),
        "customer_id": clean["customer_id"] or None,
        "batch_id": batch_id,
        "loaded_at": loaded_at,
    }
