"""Generate deterministic, fully synthetic sales datasets.

  data/sample_sales.csv              600 clean records (should pass with no issues)
  data/sample_sales_with_errors.csv  240 records with deliberately injected problems
  data/sample_sales_high_error.csv   80 records, ~25% rejected, to trigger the rejected-rate alert

Run from the project root:  python scripts/generate_sample_data.py
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 42
OUT_DIR = Path(__file__).resolve().parent.parent / "data"
HEADER = ["order_id", "order_date", "product_id", "product_name", "category",
          "region", "quantity", "unit_price", "customer_id"]
PRODUCTS = [
    ("PRD-101", "Wireless Headphones", "Electronics", 79.99),
    ("PRD-102", "Smart Watch", "Electronics", 199.00),
    ("PRD-103", "USB-C Charger", "Electronics", 24.50),
    ("PRD-201", "Non-stick Frying Pan", "Home & Kitchen", 34.00),
    ("PRD-202", "Espresso Machine", "Home & Kitchen", 149.00),
    ("PRD-203", "Cutlery Set", "Home & Kitchen", 58.75),
    ("PRD-301", "Running Jacket", "Apparel", 89.00),
    ("PRD-302", "Cotton T-Shirt", "Apparel", 19.99),
    ("PRD-303", "Trail Sneakers", "Apparel", 110.00),
    ("PRD-401", "Notebook Pack", "Office Supplies", 9.50),
    ("PRD-402", "Desk Organiser", "Office Supplies", 27.00),
    ("PRD-501", "Data Science Handbook", "Books", 45.00),
]
PRODUCT_WEIGHTS = [9, 4, 12, 6, 2, 5, 7, 11, 4, 10, 6, 3]
REGIONS = ["North", "South", "East", "West", "Central"]
REGION_WEIGHTS = [22, 20, 19, 23, 16]
QUANTITIES = [1, 2, 3, 4, 5, 6, 8, 10]
QUANTITY_WEIGHTS = [30, 25, 15, 10, 8, 5, 4, 3]
START, END = date(2025, 1, 1), date(2026, 9, 30)


def _random_order_date(rng: random.Random) -> date:
    """Seasonal pattern: November and December carry more orders."""
    span = (END - START).days
    while True:
        day = START + timedelta(days=rng.randrange(span + 1))
        weight = 1.0 if day.month not in (11, 12) else 1.6
        if rng.random() < weight / 1.6:
            return day


def _generate(rng: random.Random, count: int) -> list[dict]:
    rows = []
    for _ in range(count):
        pid, name, category, price = rng.choices(PRODUCTS, weights=PRODUCT_WEIGHTS)[0]
        rows.append({
            "order_date": _random_order_date(rng).isoformat(),
            "product_id": pid,
            "product_name": name,
            "category": category,
            "region": rng.choices(REGIONS, weights=REGION_WEIGHTS)[0],
            "quantity": str(rng.choices(QUANTITIES, weights=QUANTITY_WEIGHTS)[0]),
            "unit_price": f"{price:.2f}",
            "customer_id": f"CUST-{rng.randint(1001, 1300)}",
        })
    rows.sort(key=lambda r: r["order_date"])  # chronological file, like a real export
    return rows


def _assign_ids(rows: list[dict], start_id: int) -> None:
    for offset, row in enumerate(rows):
        row["order_id"] = f"ORD-{start_id + offset}"


def _write(path: Path, rows: list[dict], extra_lines: dict[int, str] | None = None) -> None:
    """Write rows with csv.writer; extra_lines inserts raw text lines (used for a malformed row)."""
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(HEADER)
        for index, row in enumerate(rows):
            if extra_lines and index in extra_lines:
                fh.write(extra_lines[index] + "\n")
            writer.writerow([row[c] for c in HEADER])


def build_clean(rng: random.Random) -> list[dict]:
    rows = _generate(rng, 600)
    _assign_ids(rows, 100001)
    return rows


def build_dirty(rng: random.Random, clean_rows: list[dict]) -> list[dict]:
    rows = _generate(rng, 240)
    _assign_ids(rows, 100601)

    # Deliberate problems, one per index so each is easy to find in the Data Quality page.
    rows[5]["quantity"] = ""                          # VR-001 missing quantity
    rows[12]["order_date"] = ""                       # VR-001 missing date
    rows[20]["quantity"] = "-3"                       # VR-007 negative quantity
    rows[27]["quantity"] = "0"                        # VR-007 zero quantity
    rows[33]["order_date"] = "31/02/2025"             # VR-004 wrong format / impossible date
    rows[41]["order_date"] = "2025-13-01"             # VR-004 invalid month
    rows[48]["order_date"] = "not a date"             # VR-004
    rows[55]["unit_price"] = "-19.99"                 # VR-009 negative price
    rows[60]["unit_price"] = "0"                      # VR-009 zero price
    rows[66]["unit_price"] = "twenty"                 # VR-008 non-numeric price
    rows[72]["quantity"] = "2.5"                      # VR-006 fractional quantity
    rows[80]["order_id"] = "X-99"                     # VR-002 invalid identifier
    rows[88]["order_id"] = ""                         # VR-001 missing order ID
    rows[95]["order_id"] = rows[94]["order_id"]       # VR-003 duplicate inside file
    rows[101]["order_id"] = rows[100]["order_id"]     # VR-003 duplicate inside file
    rows[110]["category"] = "Gadgets"                 # VR-010 flag: unexpected category
    rows[118]["region"] = "Antarctica"                # VR-011 flag: unexpected region
    rows[125]["customer_id"] = ""                     # VR-012 flag: optional field missing
    rows[131]["customer_id"] = "C-22"                 # VR-013 flag: unusual customer ID
    rows[140]["product_name"] = ""                    # VR-014 flag
    rows[150]["product_id"] = "P1"                    # VR-015 flag
    rows[160]["quantity"] = "750"                     # VR-016 flag: unusually large
    rows[170]["product_id"] = ""                      # VR-001 missing required product ID
    rows[180]["order_id"] = clean_rows[10]["order_id"]  # VR-017 once the clean sample is loaded
    return rows


def build_high_error(rng: random.Random) -> list[dict]:
    rows = _generate(rng, 80)
    _assign_ids(rows, 102001)
    for index in range(0, 80, 4):                     # every 4th record gets a negative quantity
        rows[index]["quantity"] = str(-1 - (index % 3))
    return rows


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    clean = build_clean(rng)
    dirty = build_dirty(rng, clean)
    _write(OUT_DIR / "sample_sales.csv", clean)
    # A malformed line (too many fields) is inserted at position 50 to test graceful skipping.
    malformed = "ORD-199999,2025-05-01,PRD-101,Wireless Headphones,Electronics,North,1,79.99,CUST-1001,EXTRA,FIELDS"
    _write(OUT_DIR / "sample_sales_with_errors.csv", dirty, extra_lines={50: malformed})
    high_error = build_high_error(rng)
    _write(OUT_DIR / "sample_sales_high_error.csv", high_error)
    print(f"Wrote {len(clean)} clean, {len(dirty)} dirty and {len(high_error)} high-error records to {OUT_DIR}")


if __name__ == "__main__":
    main()
