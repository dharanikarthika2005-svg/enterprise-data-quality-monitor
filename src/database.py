"""SQLite storage: schema, connections, transactions and queries.

Timestamps are stored as UTC ISO-8601 strings (for example 2026-10-16T09:30:00+00:00).
Connections run in autocommit mode; each write group is wrapped in an explicit
BEGIN IMMEDIATE ... COMMIT / ROLLBACK block via transaction().
"""
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src import config

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS processing_batches (
    batch_id            TEXT PRIMARY KEY,
    file_name           TEXT NOT NULL,
    checksum_sha256     TEXT NOT NULL,
    size_bytes          INTEGER NOT NULL DEFAULT 0,
    submitted_at        TEXT NOT NULL,
    started_at          TEXT,
    finished_at         TEXT,
    duration_seconds    REAL,
    status              TEXT NOT NULL CHECK (status IN
                        ('Pending','Processing','Completed','Completed with Issues','Failed')),
    total_received          INTEGER NOT NULL DEFAULT 0,
    accepted_count          INTEGER NOT NULL DEFAULT 0,
    flagged_count           INTEGER NOT NULL DEFAULT 0,
    rejected_count          INTEGER NOT NULL DEFAULT 0,
    duplicate_count         INTEGER NOT NULL DEFAULT 0,
    loaded_count            INTEGER NOT NULL DEFAULT 0,
    malformed_lines         INTEGER NOT NULL DEFAULT 0,
    required_checks_total   INTEGER NOT NULL DEFAULT 0,
    required_checks_failed  INTEGER NOT NULL DEFAULT 0,
    value_checks_total      INTEGER NOT NULL DEFAULT 0,
    value_checks_failed     INTEGER NOT NULL DEFAULT 0,
    error_message           TEXT
);
CREATE INDEX IF NOT EXISTS idx_batches_checksum ON processing_batches(checksum_sha256, status);

CREATE TABLE IF NOT EXISTS file_imports (
    import_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name       TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    size_bytes      INTEGER NOT NULL,
    submitted_at    TEXT NOT NULL,
    outcome         TEXT NOT NULL CHECK (outcome IN ('processed','reprocessed','blocked_duplicate')),
    batch_id        TEXT REFERENCES processing_batches(batch_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS staged_records (
    record_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id    TEXT NOT NULL REFERENCES processing_batches(batch_id) ON DELETE CASCADE,
    row_number  INTEGER NOT NULL,
    order_id    TEXT,
    status      TEXT NOT NULL CHECK (status IN ('accepted','flagged','rejected','duplicate')),
    raw_json    TEXT NOT NULL,
    UNIQUE (batch_id, row_number)
);

CREATE TABLE IF NOT EXISTS validation_issues (
    issue_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id   INTEGER NOT NULL REFERENCES staged_records(record_id) ON DELETE CASCADE,
    batch_id    TEXT NOT NULL REFERENCES processing_batches(batch_id) ON DELETE CASCADE,
    rule_id     TEXT NOT NULL,
    severity    TEXT NOT NULL CHECK (severity IN ('reject','flag')),
    message     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_issues_batch_rule ON validation_issues(batch_id, rule_id);

CREATE TABLE IF NOT EXISTS sales (
    sale_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     TEXT NOT NULL UNIQUE,
    order_date   TEXT NOT NULL,
    month        TEXT NOT NULL,
    product_id   TEXT NOT NULL,
    product_name TEXT,
    category     TEXT NOT NULL,
    region       TEXT NOT NULL,
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    unit_price   REAL NOT NULL CHECK (unit_price > 0),
    line_revenue REAL NOT NULL,
    customer_id  TEXT,
    batch_id     TEXT NOT NULL REFERENCES processing_batches(batch_id),
    loaded_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(order_date);
CREATE INDEX IF NOT EXISTS idx_sales_region ON sales(region);
CREATE INDEX IF NOT EXISTS idx_sales_category ON sales(category);
"""

# Column names are code constants (never user input), so building the SET clause from them is safe.
COUNT_COLUMNS = (
    "total_received", "accepted_count", "flagged_count", "rejected_count", "duplicate_count",
    "loaded_count", "malformed_lines", "required_checks_total", "required_checks_failed",
    "value_checks_total", "value_checks_failed",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _seconds_between(start_iso: str, end_iso: str) -> float:
    delta = datetime.fromisoformat(end_iso) - datetime.fromisoformat(start_iso)
    return round(delta.total_seconds(), 3)


def get_connection(db_path=None) -> sqlite3.Connection:
    path = Path(db_path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def open_connection(db_path=None):
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path=None) -> None:
    """Create tables and indexes if missing. Safe to call on every start-up."""
    with open_connection(db_path) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def transaction(conn: sqlite3.Connection):
    """All-or-nothing block: COMMIT on success, ROLLBACK on any exception."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


# ---- Writes ---------------------------------------------------------------

def find_completed_batch_by_checksum(conn, checksum: str):
    return conn.execute(
        """SELECT batch_id, file_name, finished_at FROM processing_batches
           WHERE checksum_sha256 = ? AND status IN ('Completed', 'Completed with Issues')
           ORDER BY submitted_at LIMIT 1""",
        (checksum,),
    ).fetchone()


def insert_batch(conn, batch_id, file_name, checksum, size, submitted_at, started_at) -> None:
    conn.execute(
        """INSERT INTO processing_batches
           (batch_id, file_name, checksum_sha256, size_bytes, submitted_at, started_at, status)
           VALUES (?, ?, ?, ?, ?, ?, 'Processing')""",
        (batch_id, file_name, checksum, size, submitted_at, started_at),
    )


def insert_file_import(conn, file_name, checksum, size, submitted_at, outcome, batch_id) -> None:
    conn.execute(
        """INSERT INTO file_imports (file_name, checksum_sha256, size_bytes, submitted_at, outcome, batch_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (file_name, checksum, size, submitted_at, outcome, batch_id),
    )


def insert_staged_record(conn, batch_id, row_number, order_id, status, raw: dict) -> int:
    cur = conn.execute(
        """INSERT INTO staged_records (batch_id, row_number, order_id, status, raw_json)
           VALUES (?, ?, ?, ?, ?)""",
        (batch_id, row_number, order_id, status, json.dumps(raw, ensure_ascii=False)),
    )
    return cur.lastrowid


def insert_issue(conn, record_id, batch_id, rule_id, severity, message) -> None:
    conn.execute(
        """INSERT INTO validation_issues (record_id, batch_id, rule_id, severity, message)
           VALUES (?, ?, ?, ?, ?)""",
        (record_id, batch_id, rule_id, severity, message),
    )


def insert_sale(conn, row: dict) -> None:
    conn.execute(
        """INSERT INTO sales (order_id, order_date, month, product_id, product_name, category, region,
                              quantity, unit_price, line_revenue, customer_id, batch_id, loaded_at)
           VALUES (:order_id, :order_date, :month, :product_id, :product_name, :category, :region,
                   :quantity, :unit_price, :line_revenue, :customer_id, :batch_id, :loaded_at)""",
        row,
    )


def finalise_batch(conn, batch_id, status, counts: dict, started_at) -> None:
    """Write the final status and totals. Call inside a transaction."""
    finished = utc_now()
    assignments = ", ".join(f"{c} = ?" for c in COUNT_COLUMNS)
    values = [counts.get(c, 0) for c in COUNT_COLUMNS]
    conn.execute(
        f"""UPDATE processing_batches
            SET status = ?, finished_at = ?, duration_seconds = ?, {assignments}
            WHERE batch_id = ?""",
        [status, finished, _seconds_between(started_at, finished), *values, batch_id],
    )


def mark_failed(conn, batch_id: str, started_at: str, message: str) -> None:
    finished = utc_now()
    with transaction(conn):
        conn.execute(
            """UPDATE processing_batches
               SET status = 'Failed', finished_at = ?, duration_seconds = ?, error_message = ?
               WHERE batch_id = ?""",
            (finished, _seconds_between(started_at, finished), message[:500], batch_id),
        )


# ---- Reads ----------------------------------------------------------------

def sales_order_ids(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT order_id FROM sales")}


def count_sales(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]


def fetch_batches(conn) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT * FROM processing_batches ORDER BY submitted_at DESC, batch_id DESC", conn
    )


def fetch_batch(conn, batch_id: str):
    return conn.execute("SELECT * FROM processing_batches WHERE batch_id = ?", (batch_id,)).fetchone()


def fetch_file_imports(conn) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM file_imports ORDER BY import_id DESC", conn)


def fetch_issue_rows(conn, batch_id: str) -> pd.DataFrame:
    """Every staged record joined to its issues. Accepted records appear once with null rule columns."""
    return pd.read_sql_query(
        """SELECT s.row_number, s.order_id, s.status, s.raw_json,
                  i.rule_id, i.severity, i.message
           FROM staged_records s
           LEFT JOIN validation_issues i ON i.record_id = s.record_id
           WHERE s.batch_id = ?
           ORDER BY s.row_number, i.issue_id""",
        conn, params=(batch_id,),
    )
