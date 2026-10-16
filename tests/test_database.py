import sqlite3

import pytest

from src.database import init_db, insert_batch, insert_sale, open_connection, transaction, utc_now


def _sale(order_id="ORD-1", batch="B1", qty=1, price=10.0):
    return {"order_id": order_id, "order_date": "2025-01-01", "month": "2025-01", "product_id": "PRD-101",
            "product_name": "X", "category": "Books", "region": "North", "quantity": qty,
            "unit_price": price, "line_revenue": qty * price, "customer_id": None,
            "batch_id": batch, "loaded_at": utc_now()}


def _seed_batch(conn, batch_id="B1"):
    now = utc_now()
    insert_batch(conn, batch_id, "f.csv", "chk", 10, now, now)


def test_schema_creates_all_tables(db_path):
    with open_connection(db_path) as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"sales", "processing_batches", "validation_issues", "file_imports", "staged_records"} <= names


def test_init_is_idempotent(db_path):
    init_db(db_path)
    init_db(db_path)


def test_unique_order_id_constraint_is_enforced(db_path):
    with open_connection(db_path) as conn:
        _seed_batch(conn)
        insert_sale(conn, _sale("ORD-9"))
        with pytest.raises(sqlite3.IntegrityError):
            insert_sale(conn, _sale("ORD-9"))


def test_quantity_check_constraint_is_enforced(db_path):
    with open_connection(db_path) as conn:
        _seed_batch(conn)
        with pytest.raises(sqlite3.IntegrityError):
            insert_sale(conn, _sale("ORD-10", qty=0))


def test_foreign_key_requires_existing_batch(db_path):
    with open_connection(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            insert_sale(conn, _sale("ORD-11", batch="missing"))


def test_transaction_rolls_back_on_error(db_path):
    with open_connection(db_path) as conn:
        _seed_batch(conn)
        with pytest.raises(RuntimeError):
            with transaction(conn):
                insert_sale(conn, _sale("ORD-20"))
                insert_sale(conn, _sale("ORD-21"))
                raise RuntimeError("simulated failure")
        count = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    assert count == 0


def test_transaction_commits_on_success(db_path):
    with open_connection(db_path) as conn:
        _seed_batch(conn)
        with transaction(conn):
            insert_sale(conn, _sale("ORD-30"))
        assert conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 1
