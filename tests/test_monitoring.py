from src.monitoring import compare_batches, evaluate_batch_alerts, overall_quality
import pandas as pd


def _batch(batch_id="B1", status="Completed with Issues", **overrides):
    base = dict(batch_id=batch_id, file_name="f.csv", submitted_at="2026-01-01T00:00:00+00:00",
                status=status, total_received=10, accepted_count=9, flagged_count=0, rejected_count=1,
                duplicate_count=0, required_checks_total=70, required_checks_failed=0,
                value_checks_total=40, value_checks_failed=0, duration_seconds=2.0)
    base.update(overrides)
    return base


def test_rejected_rate_above_threshold_triggers_alert():
    alerts = evaluate_batch_alerts(_batch(rejected_count=3, accepted_count=7))
    rejected = [a for a in alerts if a.metric == "rejected_rate"]
    assert len(rejected) == 1
    assert rejected[0].actual == 30.0
    assert rejected[0].threshold == 10.0
    assert rejected[0].batch_id == "B1"
    assert "above the maximum" in rejected[0].explanation
    assert rejected[0].recommendation


def test_healthy_batch_triggers_no_alerts():
    assert evaluate_batch_alerts(_batch(rejected_count=0, accepted_count=10, status="Completed")) == []


def test_failed_batch_is_not_evaluated():
    assert evaluate_batch_alerts(_batch(status="Failed", rejected_count=10)) == []


def test_pass_rate_below_minimum_triggers_alert():
    alerts = evaluate_batch_alerts(_batch(rejected_count=5, accepted_count=5))
    assert any(a.metric == "validation_pass_rate" and a.direction == "min" for a in alerts)


def test_comparison_reports_improvement_and_deterioration():
    worse = _batch("A", rejected_count=3, accepted_count=7)
    better = _batch("B", rejected_count=1, accepted_count=9)
    table = compare_batches(worse, better).set_index("Metric")
    assert table.loc["Rejected-record rate", "Verdict"] == "Improved"
    assert table.loc["Validation pass rate", "Verdict"] == "Improved"
    back = compare_batches(better, worse).set_index("Metric")
    assert back.loc["Rejected-record rate", "Verdict"] == "Deteriorated"


def test_overall_quality_pools_completed_batches_only():
    batches = pd.DataFrame([
        _batch("A", total_received=10, accepted_count=9, rejected_count=1),
        _batch("B", total_received=10, accepted_count=5, rejected_count=5),
        _batch("C", status="Failed", total_received=0, accepted_count=0, rejected_count=0),
    ])
    assert overall_quality(batches) == 70.0


def test_overall_quality_empty_is_none():
    assert overall_quality(pd.DataFrame()) is None
