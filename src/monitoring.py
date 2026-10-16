"""Cross-batch monitoring: deterministic threshold alerts, batch comparison and trend data."""
from dataclasses import dataclass

import pandas as pd

from src import config
from src.metrics import compute_quality_metrics

COMPLETED_STATUSES = ("Completed", "Completed with Issues")

METRIC_LABELS = {
    "validation_pass_rate": "Validation pass rate",
    "rejected_rate": "Rejected-record rate",
    "duplicate_rate": "Duplicate rate",
    "missing_value_rate": "Missing-value rate",
    "invalid_value_rate": "Invalid-value rate",
    "duration_seconds": "Processing duration",
}
HIGHER_IS_BETTER = {"validation_pass_rate"}

RECOMMENDATIONS = {
    "rejected_rate": "Open Data Quality, filter for 'reject' severity and fix the most frequent rule at its source system.",
    "duplicate_rate": "Check whether the export was generated twice or overlaps an earlier file; compare order IDs with the sales table.",
    "missing_value_rate": "Find the required column that is blank most often and check the upstream form or export mapping.",
    "invalid_value_rate": "Inspect the invalid dates, numbers and IDs and confirm the source system's export format.",
    "validation_pass_rate": "Review rejected and flagged records; the pass rate is below the agreed minimum.",
    "duration_seconds": "Check the file size and server load; consider splitting very large exports into smaller batches.",
}


@dataclass
class Alert:
    batch_id: str
    file_name: str
    submitted_at: str
    metric: str
    label: str
    actual: float
    threshold: float
    direction: str
    explanation: str
    recommendation: str


def _unit(metric: str) -> str:
    return "s" if metric == "duration_seconds" else "%"


def evaluate_batch_alerts(batch) -> list[Alert]:
    """Apply config.ALERT_RULES to one completed batch. Failed or pending batches are not evaluated."""
    b = dict(batch)
    if b["status"] not in COMPLETED_STATUSES:
        return []
    metrics = compute_quality_metrics(b)
    alerts = []
    for metric, (direction, threshold) in config.ALERT_RULES.items():
        actual = metrics.get(metric)
        if actual is None:
            continue
        breached = actual > threshold if direction == "max" else actual < threshold
        if not breached:
            continue
        unit = _unit(metric)
        label = METRIC_LABELS[metric]
        relation = "above the maximum" if direction == "max" else "below the minimum"
        explanation = (
            f"{label} is {actual:.2f}{unit}, which is {relation} of {threshold:g}{unit}. "
            f"Batch {b['batch_id']} ({b['file_name']}) triggered this rule."
        )
        alerts.append(Alert(
            batch_id=b["batch_id"], file_name=b["file_name"], submitted_at=b["submitted_at"],
            metric=metric, label=label, actual=actual, threshold=threshold, direction=direction,
            explanation=explanation, recommendation=RECOMMENDATIONS[metric],
        ))
    return alerts


def all_alerts(batches: pd.DataFrame) -> list[Alert]:
    alerts: list[Alert] = []
    for _, batch in batches.iterrows():
        alerts.extend(evaluate_batch_alerts(batch.to_dict()))
    return alerts


def compare_batches(batch_a, batch_b) -> pd.DataFrame:
    """Change from batch A to batch B for each metric, with an Improved / Deteriorated verdict."""
    ma = compute_quality_metrics(dict(batch_a))
    mb = compute_quality_metrics(dict(batch_b))
    rows = []
    for metric, label in METRIC_LABELS.items():
        va, vb = ma.get(metric), mb.get(metric)
        if va is None or vb is None:
            delta, verdict = None, "Not available"
        else:
            delta = round(vb - va, 2)
            if delta == 0:
                verdict = "No change"
            else:
                better = delta > 0 if metric in HIGHER_IS_BETTER else delta < 0
                verdict = "Improved" if better else "Deteriorated"
        rows.append({"Metric": label, "Batch A": va, "Batch B": vb, "Change": delta, "Verdict": verdict})
    return pd.DataFrame(rows)


def build_trend_frame(batches: pd.DataFrame) -> pd.DataFrame:
    """One row per completed batch in submission order, with derived metrics for charting."""
    rows = []
    for _, batch in batches.iterrows():
        if batch["status"] not in COMPLETED_STATUSES:
            continue
        m = compute_quality_metrics(batch.to_dict())
        rows.append({"batch_id": batch["batch_id"], "submitted_at": batch["submitted_at"], **m})
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.sort_values("submitted_at").reset_index(drop=True)
    return frame


def overall_quality(batches: pd.DataFrame):
    """Pass rate pooled across completed batches: passing records / records received."""
    if batches.empty:
        return None
    done = batches[batches["status"].isin(COMPLETED_STATUSES)]
    total = int(done["total_received"].sum())
    if not total:
        return None
    passing = int(done["accepted_count"].sum() + done["flagged_count"].sum())
    return round(100.0 * passing / total, 2)


def batch_summary_table(batches: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, b in batches.iterrows():
        m = compute_quality_metrics(b.to_dict())
        rows.append({
            "Batch": b["batch_id"], "File": b["file_name"], "Submitted (UTC)": b["submitted_at"],
            "Status": b["status"], "Received": b["total_received"], "Accepted": b["accepted_count"],
            "Flagged": b["flagged_count"], "Rejected": b["rejected_count"],
            "Duplicates": b["duplicate_count"], "Pass rate %": m["validation_pass_rate"],
            "Duration (s)": b["duration_seconds"],
        })
    return pd.DataFrame(rows)
