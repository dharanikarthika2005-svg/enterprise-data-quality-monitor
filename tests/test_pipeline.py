import sqlite3

from src import pipeline
from src.database import open_connection
from src.pipeline import process_file
from tests.helpers import make_csv, make_row


def _sales(db_path):
    with open_connection(db_path) as conn:
        total = conn.execute("SELECT COALESCE(SUM(line_revenue), 0), COUNT(*) FROM sales").fetchone()
    return round(total[0], 2), total[1]


def _batches(db_path):
    with open_connection(db_path) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM processing_batches ORDER BY batch_id")]


THREE = [make_row(order_id="ORD-1001", qty="2", price="10.00"),
         make_row(order_id="ORD-1002", qty="1", price="5.00"),
         make_row(order_id="ORD-1003", qty="3", price="2.00")]


def test_valid_file_is_loaded_and_tracked(db_path):
    result = process_file(make_csv(THREE), "good.csv", db_path)
    assert result.status == "Completed"
    assert result.counts["loaded_count"] == 3
    assert _sales(db_path) == (31.0, 3)
    batch = _batches(db_path)[0]
    assert batch["status"] == "Completed"
    assert batch["file_name"] == "good.csv"
    assert batch["duration_seconds"] is not None


def test_line_revenue_is_derived(db_path):
    process_file(make_csv(THREE), "good.csv", db_path)
    with open_connection(db_path) as conn:
        revenue = conn.execute("SELECT line_revenue FROM sales WHERE order_id='ORD-1003'").fetchone()[0]
    assert revenue == 6.0


def test_identical_file_is_blocked_and_totals_unchanged(db_path):
    process_file(make_csv(THREE), "good.csv", db_path)
    second = process_file(make_csv(THREE), "good.csv", db_path)
    assert second.blocked_duplicate is True
    assert second.status == "Blocked"
    assert _sales(db_path) == (31.0, 3)
    assert len(_batches(db_path)) == 1
    with open_connection(db_path) as conn:
        outcomes = [r[0] for r in conn.execute("SELECT outcome FROM file_imports ORDER BY import_id")]
    assert outcomes == ["processed", "blocked_duplicate"]


def test_forced_reprocess_does_not_double_count_sales(db_path):
    process_file(make_csv(THREE), "good.csv", db_path)
    again = process_file(make_csv(THREE), "good.csv", db_path, force=True)
    assert again.status == "Completed with Issues"
    assert again.counts["duplicate_count"] == 3
    assert again.counts["loaded_count"] == 0
    assert _sales(db_path) == (31.0, 3)


def test_partial_overlap_keeps_existing_records_and_loads_new_ones(db_path):
    process_file(make_csv(THREE), "first.csv", db_path)
    overlap = [make_row(order_id="ORD-1003", qty="3", price="2.00"),
               make_row(order_id="ORD-1004", qty="1", price="4.00"),
               make_row(order_id="ORD-1005", qty="1", price="4.00")]
    result = process_file(make_csv(overlap), "second.csv", db_path)
    assert result.counts["duplicate_count"] == 1
    assert result.counts["loaded_count"] == 2
    assert _sales(db_path) == (39.0, 5)


def test_structural_failure_creates_failed_batch_and_no_sales(db_path):
    bad_header = "order_id,order_date,product_id,product_name,category,region,unit_price,customer_id"
    result = process_file(make_csv([make_row()], header=bad_header), "bad.csv", db_path)
    assert result.status == "Failed"
    assert "quantity" in result.message
    assert _sales(db_path) == (0, 0)
    batch = _batches(db_path)[0]
    assert batch["status"] == "Failed"
    assert "quantity" in batch["error_message"]


def test_database_failure_rolls_back_whole_batch(db_path, monkeypatch):
    real_insert = pipeline.insert_sale
    calls = {"n": 0}

    def flaky_insert(conn, row):
        calls["n"] += 1
        if calls["n"] == 2:
            raise sqlite3.OperationalError("disk I/O error (simulated)")
        return real_insert(conn, row)

    monkeypatch.setattr(pipeline, "insert_sale", flaky_insert)
    result = process_file(make_csv(THREE), "good.csv", db_path)
    assert result.status == "Failed"
    assert "simulated" not in result.message           # internal details are not shown to users
    assert _sales(db_path) == (0, 0)                   # the first insert was rolled back too
    with open_connection(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM staged_records").fetchone()[0] == 0
    assert _batches(db_path)[0]["status"] == "Failed"


def test_mixed_file_routes_each_status_correctly(db_path):
    rows = [make_row(order_id="ORD-1"),                 # accepted
            make_row(order_id="ORD-2", qty="-1"),       # rejected
            make_row(order_id="ORD-3", cat="Gadgets"),  # flagged, held back
            make_row(order_id="ORD-1")]                 # duplicate within file
    result = process_file(make_csv(rows), "mixed.csv", db_path)
    c = result.counts
    assert (c["accepted_count"], c["rejected_count"], c["flagged_count"], c["duplicate_count"]) == (1, 1, 1, 1)
    assert c["loaded_count"] == 1
    assert _sales(db_path) == (159.98, 1)  # only ORD-1 (2 x 79.99) is loaded
