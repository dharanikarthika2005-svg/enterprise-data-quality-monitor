from src.metrics import compute_quality_metrics, format_metric


def _batch(**overrides):
    base = dict(total_received=10, accepted_count=7, flagged_count=0, rejected_count=2, duplicate_count=1,
                required_checks_total=70, required_checks_failed=7, value_checks_total=40,
                value_checks_failed=4, duration_seconds=1.5)
    base.update(overrides)
    return base


def test_rates_use_documented_denominators():
    m = compute_quality_metrics(_batch())
    assert m["validation_pass_rate"] == 70.0      # (7 accepted + 0 flagged) / 10
    assert m["rejected_rate"] == 20.0             # 2 / 10
    assert m["duplicate_rate"] == 10.0            # 1 / 10
    assert m["missing_value_rate"] == 10.0        # 7 / 70 required checks
    assert m["invalid_value_rate"] == 10.0        # 4 / 40 value checks
    assert m["duration_seconds"] == 1.5


def test_flagged_records_count_as_passing_mandatory_rules():
    m = compute_quality_metrics(_batch(accepted_count=5, flagged_count=2))
    assert m["validation_pass_rate"] == 70.0


def test_record_level_outcomes_partition_the_batch():
    b = _batch(accepted_count=5, flagged_count=2, rejected_count=2, duplicate_count=1)
    m = compute_quality_metrics(b)
    assert round(m["validation_pass_rate"] + m["rejected_rate"] + m["duplicate_rate"], 2) == 100.0


def test_zero_records_give_not_available_not_division_error():
    m = compute_quality_metrics(_batch(total_received=0, required_checks_total=0, value_checks_total=0,
                                       accepted_count=0, rejected_count=0, duplicate_count=0))
    assert m["validation_pass_rate"] is None
    assert m["missing_value_rate"] is None
    assert format_metric(m["validation_pass_rate"]) == "Not available"


def test_format_metric_shows_two_decimals():
    assert format_metric(12.345) == "12.35%"
