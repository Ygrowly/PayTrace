"""Tests for DuckDBAnalyticsSource (plan § 9.1)."""

import pytest

from app.analytics.base import (
    BenefitQuery,
    BreakdownQuery,
    FunnelQuery,
    PaymentAnalyticsSource,
    PaymentEventQuery,
)
from app.analytics.duckdb_source import DuckDBAnalyticsSource
from app.domain.events import FUNNEL_STAGE_ORDER
from app.harness.scenarios.generator import ScenarioConfig, generate_scenario
from app.harness.scenarios.io import write_dataset


@pytest.fixture(scope="module")
def datasets(tmp_path_factory):
    """Materialise small datasets for each scenario kind once per module."""
    root = tmp_path_factory.mktemp("datasets")
    refs = {}
    for kind in ("normal", "benefit_friction", "channel_timeout", "mixed_failure", "data_gap"):
        events, _ = generate_scenario(ScenarioConfig(kind=kind, seed=42, num_intents=400))
        refs[kind] = write_dataset(events, root, kind)
    return refs


@pytest.fixture(scope="module")
def source():
    return DuckDBAnalyticsSource()


def test_implements_protocol(source):
    assert isinstance(source, PaymentAnalyticsSource)


def test_funnel_normal_has_no_anomalies(source, datasets):
    res = source.get_funnel(FunnelQuery(dataset_ref=datasets["normal"].path))
    assert res.baseline.order_confirmed_count == 400
    assert res.incident.order_confirmed_count == 400
    assert len(res.baseline.stages) == len(FUNNEL_STAGE_ORDER)
    assert res.anomalous_stages == []
    # First stage overall rate is 1.0 by construction.
    assert res.baseline.stages[0].overall_rate == 1.0
    # Rates are monotonically non-increasing down the funnel.
    rates = [s.overall_rate for s in res.incident.stages]
    assert rates == sorted(rates, reverse=True)


def test_funnel_channel_timeout_flags_channel_stage(source, datasets):
    res = source.get_funnel(FunnelQuery(dataset_ref=datasets["channel_timeout"].path))
    assert "CHANNEL_SUCCEEDED" in res.anomalous_stages


def test_funnel_dimension_filter(source, datasets):
    res = source.get_funnel(
        FunnelQuery(
            dataset_ref=datasets["channel_timeout"].path,
            filters={"payment_channel": "channel_b"},
        )
    )
    # Restricted to the injected channel, the drop should be larger.
    assert "CHANNEL_SUCCEEDED" in res.anomalous_stages


def test_funnel_rejects_unknown_dimension(source, datasets):
    with pytest.raises(ValueError, match="whitelist"):
        source.get_funnel(
            FunnelQuery(
                dataset_ref=datasets["normal"].path,
                filters={"user_id_hash": "x"},
            )
        )


def test_breakdown_whitelist_enforced(source, datasets):
    with pytest.raises(ValueError, match="whitelist"):
        source.breakdown_loss(
            BreakdownQuery(
                dataset_ref=datasets["normal"].path, dimension="event_id; DROP TABLE events"
            )
        )


def test_breakdown_channel_timeout_pinpoints_channel_b(source, datasets):
    res = source.breakdown_loss(
        BreakdownQuery(dataset_ref=datasets["channel_timeout"].path, dimension="payment_channel")
    )
    assert res.rows, "expected rows"
    top = res.rows[0]
    assert top.dimension_value == "channel_b"
    assert top.rate_delta < 0
    assert top.estimated_lost_intents > 0


def test_breakdown_top_k_capped(source, datasets):
    res = source.breakdown_loss(
        BreakdownQuery(dataset_ref=datasets["normal"].path, dimension="region", top_k=2)
    )
    assert len(res.rows) <= 2


def test_benefit_gap_friction_shift(source, datasets):
    res = source.analyze_benefit_gap(BenefitQuery(dataset_ref=datasets["benefit_friction"].path))
    assert res.mean_gap_shift_minor > 500  # injected shift is +1200
    high = next(b for b in res.incident.buckets if b.bucket == ">=1000")
    low = next(b for b in res.incident.buckets if b.bucket == "0-300")
    assert high.cancel_rate > low.cancel_rate
    assert high.intent_count > 0


def test_benefit_gap_normal_small_shift(source, datasets):
    res = source.analyze_benefit_gap(BenefitQuery(dataset_ref=datasets["normal"].path))
    assert abs(res.mean_gap_shift_minor) < 100


def test_inspect_events_timeout_signature(source, datasets):
    res = source.inspect_payment_events(
        PaymentEventQuery(dataset_ref=datasets["channel_timeout"].path)
    )
    assert res.incident.status_counts.get("TIMEOUT", 0) > 0
    codes = {e.error_code for e in res.incident.top_error_codes}
    assert "CHANNEL_TIMEOUT" in codes
    assert "channel_b" in res.incident.affected_payment_channels
    assert res.incident.latency.p95_ms is not None


def test_inspect_events_normal_clean(source, datasets):
    res = source.inspect_payment_events(PaymentEventQuery(dataset_ref=datasets["normal"].path))
    assert res.incident.status_counts.get("TIMEOUT", 0) == 0
    assert res.incident.top_error_codes == []


def test_validate_dataset_ok(source, datasets):
    res = source.validate_dataset(datasets["normal"].path)
    assert res.ok
    assert res.duplicate_event_ids == 0
    assert res.missing_stages == []
    assert res.row_count > 0


def test_validate_dataset_data_gap_warns(source, datasets):
    res = source.validate_dataset(datasets["data_gap"].path)
    assert not res.ok
    assert "AUTHENTICATION_PASSED" in res.missing_stages
    assert "CHANNEL_SUCCEEDED" in res.missing_stages
    assert any("missing funnel stages" in w for w in res.warnings)
    assert any("benefit_id null rate" in w for w in res.warnings)


def test_validate_dataset_missing_file(source):
    with pytest.raises(FileNotFoundError):
        source.validate_dataset("does/not/exist.parquet")
