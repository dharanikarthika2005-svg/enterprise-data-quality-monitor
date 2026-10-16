"""Data-quality metrics. Each rate states its denominator. A zero denominator gives None ("Not available")."""
from typing import Mapping, Optional


def pct(numerator: float, denominator: float) -> Optional[float]:
    if not denominator:
        return None
    return round(100.0 * numerator / denominator, 2)


def compute_quality_metrics(batch: Mapping) -> dict:
    """Derive rates from stored counts. Flagged records count as passing the mandatory rules."""
    b = dict(batch)
    total = b.get("total_received") or 0
    return {
        # records passing all mandatory rules / records assessed
        "validation_pass_rate": pct((b.get("accepted_count") or 0) + (b.get("flagged_count") or 0), total),
        # record-level: rejected records / records assessed
        "rejected_rate": pct(b.get("rejected_count") or 0, total),
        # record-level: duplicate records / records assessed
        "duplicate_rate": pct(b.get("duplicate_count") or 0, total),
        # field-level: failed required-field checks / applicable required-field checks
        "missing_value_rate": pct(b.get("required_checks_failed") or 0, b.get("required_checks_total") or 0),
        # field-level: failed format/type checks / applicable format/type checks
        "invalid_value_rate": pct(b.get("value_checks_failed") or 0, b.get("value_checks_total") or 0),
        "duration_seconds": b.get("duration_seconds"),
    }


def format_metric(value, unit: str = "%") -> str:
    if value is None:
        return "Not available"
    return f"{value:,.2f}{unit}"
