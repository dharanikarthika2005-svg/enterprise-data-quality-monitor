"""Extract step: file-level checks, checksum and CSV parsing.
Raises IngestionError with messages that are safe to show in the dashboard."""
import hashlib
import io
import logging
from dataclasses import dataclass, field

import pandas as pd

from src import config
from src.transformation import clean_string_values, standardise_columns

logger = logging.getLogger(__name__)


class IngestionError(Exception):
    """A problem with the file itself. The message is safe to display to users."""


@dataclass
class LoadedFile:
    file_name: str
    checksum: str
    size_bytes: int
    frame: pd.DataFrame
    malformed_count: int = 0
    malformed_samples: list[str] = field(default_factory=list)


def compute_checksum(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_csv(raw: bytes, file_name: str) -> LoadedFile:
    """Parse uploaded bytes into a text-only DataFrame with a row_number column (1-based data rows)."""
    if not file_name or not file_name.lower().endswith(config.ALLOWED_EXTENSIONS):
        raise IngestionError("Only .csv files are supported.")
    if not raw or not raw.strip():
        raise IngestionError("The file is empty.")
    if len(raw) > config.MAX_UPLOAD_BYTES:
        mb = config.MAX_UPLOAD_BYTES // (1024 * 1024)
        raise IngestionError(f"The file is larger than the {mb} MB limit.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise IngestionError("The file must be UTF-8 encoded text.") from None

    malformed: list[str] = []

    def keep_malformed(fields):
        malformed.append(",".join(str(f) for f in fields)[:200])
        return None  # skip the line but remember that it existed

    try:
        frame = pd.read_csv(
            io.StringIO(text), dtype=str, keep_default_na=False,
            engine="python", on_bad_lines=keep_malformed,
        )
    except pd.errors.EmptyDataError:
        raise IngestionError("The file has no header row.") from None
    except pd.errors.ParserError as exc:
        raise IngestionError(f"The file could not be parsed as CSV: {exc}") from None

    frame = standardise_columns(frame)
    missing = [c for c in config.REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise IngestionError(
            f"Missing required column(s): {', '.join(missing)}. "
            f"Expected: {', '.join(config.REQUIRED_COLUMNS)}."
        )
    if frame.empty:
        raise IngestionError("The file has a header but no data rows.")

    frame = clean_string_values(frame)
    frame.insert(0, "row_number", range(1, len(frame) + 1))
    if malformed:
        logger.warning("Skipped %d malformed line(s) in %s", len(malformed), file_name)
    return LoadedFile(
        file_name=file_name,
        checksum=compute_checksum(raw),
        size_bytes=len(raw),
        frame=frame,
        malformed_count=len(malformed),
        malformed_samples=malformed[:5],
    )
