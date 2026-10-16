from datetime import date

from src.ingestion import load_csv
from src.validation import RULES, build_error_report, validate_records
from tests.helpers import make_csv, make_row

TODAY = date(2026, 10, 16)


def run(rows, existing=None):
    loaded = load_csv(make_csv(rows), "t.csv")
    return validate_records(loaded.frame, existing or set(), today=TODAY)


def rules_of(result, index=0):
    return [rule for rule, _ in result.records[index]["issues"]]


def test_valid_record_is_accepted_and_parsed():
    result = run([make_row(qty="2", price="79.99")])
    record = result.records[0]
    assert record["status"] == "accepted"
    assert record["clean"]["quantity"] == 2
    assert record["clean"]["unit_price"] == 79.99
    assert record["clean"]["order_date"] == date(2025, 3, 10)


def test_negative_quantity_is_rejected():
    result = run([make_row(qty="-3")])
    assert result.records[0]["status"] == "rejected"
    assert "VR-007" in rules_of(result)


def test_zero_quantity_is_rejected():
    assert "VR-007" in rules_of(run([make_row(qty="0")]))


def test_invalid_date_is_rejected():
    result = run([make_row(date="31/02/2025")])
    assert result.records[0]["status"] == "rejected"
    assert "VR-004" in rules_of(result)


def test_future_date_is_rejected():
    assert "VR-005" in rules_of(run([make_row(date="2026-12-01")]))


def test_missing_required_value_is_rejected():
    result = run([make_row(qty="")])
    assert result.records[0]["status"] == "rejected"
    assert "VR-001" in rules_of(result)


def test_non_numeric_price_is_rejected():
    assert "VR-008" in rules_of(run([make_row(price="twenty")]))


def test_zero_or_negative_price_is_rejected():
    assert "VR-009" in rules_of(run([make_row(price="0")]))
    assert "VR-009" in rules_of(run([make_row(price="-5.00")]))


def test_fractional_quantity_is_rejected():
    assert "VR-006" in rules_of(run([make_row(qty="2.5")]))


def test_duplicate_inside_file_keeps_first_occurrence():
    result = run([make_row(order_id="ORD-5000"), make_row(order_id="ORD-5000", qty="5")])
    assert result.records[0]["status"] == "accepted"
    assert result.records[1]["status"] == "duplicate"
    assert "VR-003" in rules_of(result, 1)


def test_duplicate_of_existing_sale_is_detected():
    result = run([make_row(order_id="ORD-7000")], existing={"ORD-7000"})
    assert result.records[0]["status"] == "duplicate"
    assert "VR-017" in rules_of(result)


def test_unexpected_category_is_flagged_not_rejected():
    result = run([make_row(cat="Gadgets")])
    assert result.records[0]["status"] == "flagged"
    assert "VR-010" in rules_of(result)


def test_missing_customer_is_flagged():
    result = run([make_row(cust="")])
    assert result.records[0]["status"] == "flagged"
    assert "VR-012" in rules_of(result)


def test_multiple_issues_on_one_record_are_all_reported():
    result = run([make_row(qty="-1", cat="Gadgets", date="bad")])
    rules = rules_of(result)
    assert {"VR-007", "VR-010", "VR-004"} <= set(rules)
    assert result.records[0]["status"] == "rejected"


def test_required_check_denominator_is_fields_times_rows():
    result = run([make_row(), make_row(order_id="ORD-1002"), make_row(order_id="ORD-1003")])
    assert result.checks["required_checks_total"] == 3 * 7


def test_every_issue_uses_a_registered_rule_id():
    result = run([make_row(qty="-1", cat="X", region="Y", price="abc", date="nope", cust="C-1", pid="P1")])
    for _, rule_id in [(None, r) for r, _ in result.records[0]["issues"]]:
        assert rule_id in RULES


def test_error_report_contains_only_non_accepted_records():
    import pandas as pd
    import json
    issue_rows = pd.DataFrame([
        {"row_number": 1, "order_id": "ORD-1", "status": "accepted", "raw_json": json.dumps({"a": "1"}),
         "rule_id": None, "severity": None, "message": None},
        {"row_number": 2, "order_id": "ORD-2", "status": "rejected", "raw_json": json.dumps({"a": "2"}),
         "rule_id": "VR-007", "severity": "reject", "message": "Quantity must be greater than zero"},
    ])
    report = build_error_report(issue_rows)
    assert list(report["order_id"]) == ["ORD-2"]
    assert report.iloc[0]["rule_title"] == RULES["VR-007"].title
    assert report.iloc[0]["raw_a"] == "2"
