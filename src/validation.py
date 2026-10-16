"""Validation engine.

Each record is checked against the rule catalogue (RULES). A record's status is decided by its most
serious issue:  duplicate > rejected > flagged > accepted.
Values are never silently corrected: the original raw values are always preserved.
"""
import json
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from src import config


@dataclass(frozen=True)
class Rule:
    rule_id: str
    category: str
    severity: str  # "reject" or "flag"
    title: str
    condition: str


RULES: dict[str, Rule] = {rule.rule_id: rule for rule in [
    Rule("VR-001", "Missing value", "reject", "Required field is missing", "A mandatory field is blank"),
    Rule("VR-002", "Invalid identifier", "reject", "Order ID format is invalid", f"order_id does not match {config.ORDER_ID_PATTERN}"),
    Rule("VR-003", "Duplicate", "reject", "Duplicate order ID in file", "order_id already appeared earlier in the same file; the first occurrence is kept"),
    Rule("VR-004", "Invalid value", "reject", "Order date is not a valid date", f"order_date is not a real date in {config.DATE_FORMAT} format"),
    Rule("VR-005", "Business rule", "reject", "Order date is in the future", "order_date is after the processing date"),
    Rule("VR-006", "Invalid value", "reject", "Quantity is not a whole number", "quantity is not numeric or has a fractional part"),
    Rule("VR-007", "Business rule", "reject", "Quantity must be greater than zero", "quantity <= 0"),
    Rule("VR-008", "Invalid value", "reject", "Unit price is not numeric", "unit_price cannot be read as a finite number"),
    Rule("VR-009", "Business rule", "reject", "Unit price must be positive", "unit_price <= 0"),
    Rule("VR-010", "Unexpected value", "flag", "Category not in approved list", "category is not in ALLOWED_CATEGORIES"),
    Rule("VR-011", "Unexpected value", "flag", "Region not in approved list", "region is not in ALLOWED_REGIONS"),
    Rule("VR-012", "Missing value", "flag", "Customer ID is missing", "customer_id is blank (optional field)"),
    Rule("VR-013", "Invalid identifier", "flag", "Customer ID format is unusual", f"customer_id does not match {config.CUSTOMER_ID_PATTERN}"),
    Rule("VR-014", "Missing value", "flag", "Product name is missing", "product_name is blank (optional field)"),
    Rule("VR-015", "Invalid identifier", "flag", "Product ID format is unusual", f"product_id does not match {config.PRODUCT_ID_PATTERN}"),
    Rule("VR-016", "Business rule", "flag", "Unusually large quantity", f"quantity is greater than {config.MAX_QUANTITY_FLAG}"),
    Rule("VR-017", "Duplicate", "reject", "Order ID already in sales table", "order_id exists in sales from an earlier batch; the existing record is kept"),
]}

DUPLICATE_RULES = {"VR-003", "VR-017"}


@dataclass
class ValidationResult:
    records: list[dict] = field(default_factory=list)
    checks: dict = field(default_factory=lambda: {
        "required_checks_total": 0, "required_checks_failed": 0,
        "value_checks_total": 0, "value_checks_failed": 0,
    })

    def status_counts(self) -> dict:
        counts = {"accepted": 0, "flagged": 0, "rejected": 0, "duplicate": 0}
        for record in self.records:
            counts[record["status"]] += 1
        return counts


def _validate_row(raw: dict, checks: dict, today: date) -> tuple[list[tuple[str, str]], dict | None]:
    issues: list[tuple[str, str]] = []

    def add(rule_id: str, message: str) -> None:
        issues.append((rule_id, message))

    # Mandatory fields (required-field checks)
    for name in config.MANDATORY_FIELDS:
        checks["required_checks_total"] += 1
        if raw.get(name, "") == "":
            checks["required_checks_failed"] += 1
            add("VR-001", f"Required field '{name}' is missing")

    # Identifiers (value checks run only when the field is populated)
    order_id = raw.get("order_id", "")
    if order_id:
        checks["value_checks_total"] += 1
        if not re.fullmatch(config.ORDER_ID_PATTERN, order_id):
            checks["value_checks_failed"] += 1
            add("VR-002", f"Order ID '{order_id}' must look like ORD-<number>")

    product_id = raw.get("product_id", "")
    if product_id:
        checks["value_checks_total"] += 1
        if not re.fullmatch(config.PRODUCT_ID_PATTERN, product_id):
            checks["value_checks_failed"] += 1
            add("VR-015", f"Product ID '{product_id}' does not follow the expected pattern")

    if not raw.get("product_name", ""):
        add("VR-014", "Product name is missing")

    customer_id = raw.get("customer_id", "")
    if not customer_id:
        add("VR-012", "Customer ID is missing (optional, but needed for customer analysis)")
    else:
        checks["value_checks_total"] += 1
        if not re.fullmatch(config.CUSTOMER_ID_PATTERN, customer_id):
            checks["value_checks_failed"] += 1
            add("VR-013", f"Customer ID '{customer_id}' does not follow the expected pattern")

    # Dates
    parsed_date = None
    order_date = raw.get("order_date", "")
    if order_date:
        checks["value_checks_total"] += 1
        try:
            parsed_date = datetime.strptime(order_date, config.DATE_FORMAT).date()
        except ValueError:
            checks["value_checks_failed"] += 1
            add("VR-004", f"Order date '{order_date}' is not a valid {config.DATE_FORMAT} date")
        if parsed_date and parsed_date > today:
            add("VR-005", f"Order date {order_date} is in the future")

    # Quantity
    quantity = None
    raw_qty = raw.get("quantity", "")
    if raw_qty:
        checks["value_checks_total"] += 1
        try:
            number = float(raw_qty)
            if not number.is_integer():
                raise ValueError
            quantity = int(number)
        except ValueError:
            checks["value_checks_failed"] += 1
            add("VR-006", f"Quantity '{raw_qty}' must be a whole number")
        if quantity is not None:
            if quantity <= 0:
                add("VR-007", f"Quantity must be greater than zero (got {quantity})")
            elif quantity > config.MAX_QUANTITY_FLAG:
                add("VR-016", f"Quantity {quantity} is unusually large; please confirm")

    # Unit price
    unit_price = None
    raw_price = raw.get("unit_price", "")
    if raw_price:
        checks["value_checks_total"] += 1
        try:
            value = float(raw_price)
            if not math.isfinite(value):
                raise ValueError
            unit_price = value
        except ValueError:
            checks["value_checks_failed"] += 1
            add("VR-008", f"Unit price '{raw_price}' is not a number")
        if unit_price is not None and unit_price <= 0:
            add("VR-009", f"Unit price must be positive (got {raw_price})")

    # Categorical values (flag only: may be valid but unexpected)
    if raw.get("category") and raw["category"] not in config.ALLOWED_CATEGORIES:
        add("VR-010", f"Category '{raw['category']}' is not in the approved list")
    if raw.get("region") and raw["region"] not in config.ALLOWED_REGIONS:
        add("VR-011", f"Region '{raw['region']}' is not in the approved list")

    clean = None
    if order_id and parsed_date and quantity is not None and unit_price is not None:
        clean = {
            "order_id": order_id,
            "order_date": parsed_date,
            "product_id": product_id,
            "product_name": raw.get("product_name", ""),
            "category": raw.get("category", ""),
            "region": raw.get("region", ""),
            "quantity": quantity,
            "unit_price": unit_price,
            "customer_id": customer_id,
        }
    return issues, clean


def validate_records(frame: pd.DataFrame, existing_order_ids: set[str], today: date | None = None) -> ValidationResult:
    """Validate every row. `existing_order_ids` are IDs already stored in the sales table."""
    today = today or date.today()
    result = ValidationResult()
    seen_in_file: set[str] = set()

    for _, row in frame.iterrows():
        raw = {k: str(v) for k, v in row.items() if k != "row_number"}
        issues, clean = _validate_row(raw, result.checks, today)

        order_id = raw.get("order_id", "")
        if order_id:
            if order_id in seen_in_file:
                issues.insert(0, ("VR-003", f"Duplicate order ID '{order_id}' appears earlier in this file"))
            elif order_id in existing_order_ids:
                issues.insert(0, ("VR-017", f"Order ID '{order_id}' already exists in the sales table"))
            seen_in_file.add(order_id)

        rule_ids = {rule_id for rule_id, _ in issues}
        if rule_ids & DUPLICATE_RULES:
            status = "duplicate"
        elif any(RULES[r].severity == "reject" for r in rule_ids):
            status = "rejected"
        elif issues:
            status = "flagged"
        else:
            status = "accepted"

        result.records.append({
            "row_number": int(row["row_number"]),
            "order_id": order_id or None,
            "status": status,
            "raw": raw,
            "issues": issues,
            "clean": clean if status in ("accepted", "flagged") else None,
        })
    return result


def build_error_report(issue_rows: pd.DataFrame) -> pd.DataFrame:
    """Flatten joined staged-record/issue rows into a downloadable report (non-accepted records only)."""
    columns = ["row_number", "order_id", "status", "rule_id", "rule_title", "severity", "message"]
    if issue_rows.empty:
        return pd.DataFrame(columns=columns)
    df = issue_rows[issue_rows["status"] != "accepted"].copy()
    if df.empty:
        return pd.DataFrame(columns=columns)
    raw = pd.DataFrame([json.loads(s) for s in df["raw_json"]], index=df.index).add_prefix("raw_")
    out = df[["row_number", "order_id", "status", "rule_id", "severity", "message"]].copy()
    out.insert(4, "rule_title", out["rule_id"].map(lambda r: RULES[r].title if r in RULES else None))
    return pd.concat([out, raw], axis=1)
