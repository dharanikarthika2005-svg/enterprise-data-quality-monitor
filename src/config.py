"""Central configuration. Paths and limits can be overridden with environment variables where noted."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = Path(os.getenv("SALES_DB_PATH", DATA_DIR / "sales_monitor.db"))
SAMPLE_CLEAN_FILE = DATA_DIR / "sample_sales.csv"
SAMPLE_DIRTY_FILE = DATA_DIR / "sample_sales_with_errors.csv"

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
MAX_UPLOAD_BYTES = int(float(os.getenv("MAX_UPLOAD_MB", "5")) * 1024 * 1024)
ALLOWED_EXTENSIONS = (".csv",)

# Every column must be present in the file (structure check).
REQUIRED_COLUMNS = [
    "order_id", "order_date", "product_id", "product_name", "category",
    "region", "quantity", "unit_price", "customer_id",
]
# Fields that must be populated. A blank value here is a rejection (VR-001).
MANDATORY_FIELDS = ["order_id", "order_date", "product_id", "category", "region", "quantity", "unit_price"]

# Validation policy (configurable).
ALLOWED_CATEGORIES = ["Electronics", "Home & Kitchen", "Apparel", "Office Supplies", "Books"]
ALLOWED_REGIONS = ["North", "South", "East", "West", "Central"]
DATE_FORMAT = "%Y-%m-%d"
ORDER_ID_PATTERN = r"^ORD-\d+$"
PRODUCT_ID_PATTERN = r"^PRD-\d{3}$"
CUSTOMER_ID_PATTERN = r"^CUST-\d+$"
MAX_QUANTITY_FLAG = 500

# False: flagged records are stored for review but kept out of sales analytics.
# True: flagged records are loaded into the sales table as well.
LOAD_FLAGGED_RECORDS = False

# Alert thresholds: metric -> (direction, threshold). "max" alerts when above, "min" when below.
ALERT_RULES = {
    "rejected_rate": ("max", 10.0),
    "duplicate_rate": ("max", 5.0),
    "missing_value_rate": ("max", 2.0),
    "invalid_value_rate": ("max", 5.0),
    "validation_pass_rate": ("min", 90.0),
    "duration_seconds": ("max", 60.0),
}
