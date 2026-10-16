"""ETL orchestration.

Extract   -> ingestion.load_csv (file checks, checksum)
Transform -> validation.validate_records (rules, duplicates, status) + transformation.build_sales_row
Load      -> one transaction per batch: staged records, issues, sales rows and final batch totals.
             If anything fails, the whole load rolls back and the batch is recorded as Failed.
"""
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from src import config
from src.database import (
    find_completed_batch_by_checksum, finalise_batch, init_db, insert_batch, insert_file_import,
    insert_issue, insert_sale, insert_staged_record, mark_failed, open_connection,
    sales_order_ids, transaction, utc_now,
)
from src.ingestion import IngestionError, LoadedFile, compute_checksum, load_csv
from src.transformation import build_sales_row
from src.validation import RULES, validate_records

logger = logging.getLogger(__name__)

GENERIC_FAILURE = (
    "The batch could not be completed because of an internal error. "
    "No partial data was kept. Details were written to the application log."
)
COMPLETED_STATUSES = ("Completed", "Completed with Issues")


@dataclass
class ProcessingResult:
    status: str                      # final batch status, or "Failed" / "Blocked"
    message: str
    batch_id: str | None = None
    blocked_duplicate: bool = False
    previous_batch_id: str | None = None
    counts: dict = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status in COMPLETED_STATUSES


def _new_batch_id(submitted_at: str) -> str:
    stamp = datetime.fromisoformat(submitted_at).strftime("%Y%m%d%H%M%S")
    return f"B{stamp}-{uuid.uuid4().hex[:6]}"


def _should_load(status: str) -> bool:
    return status == "accepted" or (config.LOAD_FLAGGED_RECORDS and status == "flagged")


def _transform_and_load(conn, batch_id: str, loaded: LoadedFile, started_at: str) -> tuple[dict, str]:
    result = validate_records(loaded.frame, sales_order_ids(conn))
    statuses = result.status_counts()
    loaded_at = utc_now()
    loaded_count = 0

    with transaction(conn):
        for rec in result.records:
            record_id = insert_staged_record(
                conn, batch_id, rec["row_number"], rec["order_id"], rec["status"], rec["raw"]
            )
            for rule_id, message in rec["issues"]:
                insert_issue(conn, record_id, batch_id, rule_id, RULES[rule_id].severity, message)
            if _should_load(rec["status"]):
                insert_sale(conn, build_sales_row(rec["clean"], batch_id, loaded_at))
                loaded_count += 1

        counts = {
            "total_received": len(result.records),
            "accepted_count": statuses["accepted"],
            "flagged_count": statuses["flagged"],
            "rejected_count": statuses["rejected"],
            "duplicate_count": statuses["duplicate"],
            "loaded_count": loaded_count,
            "malformed_lines": loaded.malformed_count,
            **result.checks,
        }
        has_issues = statuses["rejected"] + statuses["flagged"] + statuses["duplicate"] > 0
        status = "Completed with Issues" if has_issues else "Completed"
        finalise_batch(conn, batch_id, status, counts, started_at)
    return counts, status


def _summary_message(status: str, counts: dict) -> str:
    return (
        f"Batch finished as '{status}'. Loaded {counts['loaded_count']:,} sales record(s). "
        f"Accepted {counts['accepted_count']:,}, flagged {counts['flagged_count']:,}, "
        f"rejected {counts['rejected_count']:,}, duplicates {counts['duplicate_count']:,}."
    )


def process_file(raw: bytes, file_name: str, db_path=None, force: bool = False) -> ProcessingResult:
    """Run the full ETL for one uploaded file. User-data problems return a result; they never raise."""
    init_db(db_path)
    with open_connection(db_path) as conn:
        checksum = compute_checksum(raw)
        size = len(raw)
        submitted_at = utc_now()

        previous = None if force else find_completed_batch_by_checksum(conn, checksum)
        if previous is not None:
            with transaction(conn):
                insert_file_import(conn, file_name, checksum, size, submitted_at, "blocked_duplicate", None)
            logger.info("Blocked duplicate file %s (matches batch %s)", file_name, previous["batch_id"])
            return ProcessingResult(
                status="Blocked",
                message=(
                    f"This exact file was already processed successfully in batch {previous['batch_id']}. "
                    "Nothing was loaded. Tick 'Reprocess' to run it again; sales totals will not change "
                    "because existing orders are recognised as duplicates."
                ),
                blocked_duplicate=True,
                previous_batch_id=previous["batch_id"],
            )

        batch_id = _new_batch_id(submitted_at)
        started_at = utc_now()
        with transaction(conn):
            insert_batch(conn, batch_id, file_name, checksum, size, submitted_at, started_at)
            insert_file_import(conn, file_name, checksum, size, submitted_at,
                               "reprocessed" if force else "processed", batch_id)
        logger.info("Batch %s started for file %s", batch_id, file_name)

        try:
            loaded = load_csv(raw, file_name)
            counts, status = _transform_and_load(conn, batch_id, loaded, started_at)
        except IngestionError as exc:
            mark_failed(conn, batch_id, started_at, str(exc))
            logger.warning("Batch %s rejected at file-structure check: %s", batch_id, exc)
            return ProcessingResult("Failed", str(exc), batch_id)
        except Exception:
            logger.exception("Batch %s failed unexpectedly", batch_id)
            mark_failed(conn, batch_id, started_at, GENERIC_FAILURE)
            return ProcessingResult("Failed", GENERIC_FAILURE, batch_id)

    logger.info("Batch %s finished with status %s", batch_id, status)
    return ProcessingResult(status, _summary_message(status, counts), batch_id, counts=counts)
