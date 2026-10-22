"""Tests for DuckDBAnalyticsSource (plan § 9.1)."""

import json

import pytest

from app.analytics.base import (
    BenefitQuery,
    BreakdownQuery,
    CancelReorderQuery,
    ConfigChangesQuery,
    FunnelQuery,
    PaymentAnalyticsSource,
    PaymentEventQuery,
)
from app.analytics.duckdb_source import DuckDBAnalyticsSource
from app.domain.events import FUNNEL_STAGE_ORDER
from app.harness.scenarios.generator import (
    ScenarioConfig,
    generate_config_changes,
    generate_scenario,
)
from app.harness.scenarios.io import write_dataset


@pytest.fixture(scope="module")
def datasets(tmp_path_factory):
    """Materialise small datasets for each scenario kind once per module."""
    root = tmp_path_factory.mktemp("datasets")
    refs = {}
    for kind in ("normal", "benefit_friction", "channel_timeout", "mixed_failure", "data_gap"):
        events, _ = generate_scenario(ScenarioConfig(kind=kind, seed=42, num_intents=400))
        refs[kind] = write_dataset(events, root, kind)
        # Write config changes for get_config_changes method.
        config_path = root / f"{kind}.config_changes.json"
        config_path.write_text(json.dumps(generate_config_changes(kind, seed=42)), encoding="utf-8")
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


# --- trace_cancel_and_reorder ----------------------------------------------------


def test_cancel_reorder_normal_clean(source, datasets):
    res = source.trace_cancel_and_reorder(CancelReorderQuery(dataset_ref=datasets["normal"].path))
    assert res.baseline.total_intents > 0
    assert res.incident.total_intents > 0
    # Normal scenario: minimal cancel rate delta.
    assert abs(res.deltas.cancel_rate_delta) < 0.05


def test_cancel_reorder_benefit_friction_has_delta(source, datasets):
    res = source.trace_cancel_and_reorder(
        CancelReorderQuery(dataset_ref=datasets["benefit_friction"].path)
    )
    assert res.deltas.cancel_rate_delta > 0
    assert res.deltas.estimated_extra_cancelled > 0
    assert res.incident.cancel_rate > res.baseline.cancel_rate


# --- get_config_changes ----------------------------------------------------------


def test_config_changes_mixed_failure(source, datasets):
    res = source.get_config_changes(ConfigChangesQuery(dataset_ref=datasets["mixed_failure"].path))
    assert len(res.incident_window_changes) == 2
    types = {c.change_type for c in res.incident_window_changes}
    assert types == {"promo_rule", "routing"}


def test_config_changes_normal_empty(source, datasets):
    res = source.get_config_changes(ConfigChangesQuery(dataset_ref=datasets["normal"].path))
    assert res.incident_window_changes == []
    assert res.baseline_window_changes == []


def test_config_changes_filter_by_type(source, datasets):
    res = source.get_config_changes(
        ConfigChangesQuery(dataset_ref=datasets["mixed_failure"].path, change_types=["routing"])
    )
    assert len(res.incident_window_changes) == 1
    assert res.incident_window_changes[0].change_type == "routing"


def test_config_changes_data_gap_returns_empty(source, datasets):
    """data_gap has no fault-injected config changes — result is empty."""
    res = source.get_config_changes(ConfigChangesQuery(dataset_ref=datasets["data_gap"].path))
    assert res.incident_window_changes == []
    assert res.baseline_window_changes == []


def test_validate_dataset_missing_file(source):
    with pytest.raises(FileNotFoundError):
        source.validate_dataset("does/not/exist.parquet")


# ---------------------------------------------------------------------------
# Loss attribution must not double-count across stages (notes § 6.3)
# ---------------------------------------------------------------------------


def test_stage_loss_bases_are_nested_so_no_intent_is_counted_twice(source, datasets):
    """Each stage's loss is measured over the incident population that entered it.

    That population is the one which reached the previous stage, so it excludes
    intents that already dropped out upstream. Estimating every stage from its
    own overall rate instead charges the same intent again at each downstream
    stage — the double-count that makes a two-root-cause incident report more
    loss than it observed.
    """
    for kind in ("benefit_friction", "channel_timeout", "mixed_failure"):
        result = source.get_funnel(FunnelQuery(dataset_ref=datasets[kind].path))
        incident_counts = {s.stage: s.reached_count for s in result.incident.stages}
        order = [s.stage for s in result.incident.stages]

        for index, delta in enumerate(result.deltas):
            if index == 0:
                assert delta.estimated_lost_intents == 0
                continue
            entering = incident_counts[order[index - 1]]
            assert delta.estimated_lost_intents <= entering, (
                f"{kind}/{delta.stage}: attributed {delta.estimated_lost_intents} "
                f"but only {entering} intents entered the transition"
            )


def test_loss_attribution_tracks_the_injected_impact(source, tmp_path):
    """The attributed loss must land near the fault's true impact.

    This is the end-to-end claim behind the dedup fix: with per-stage overall
    rates, `mixed_failure` over-attributed by ~38%; with per-transition step
    rates it lands within a third.

    Measured at 5000 intents on purpose. The estimator extrapolates a rate
    delta per transition, so its error is sampling noise that accumulates across
    stages: at 400 intents the total can be off by ~45% even though the
    estimate is unbiased. Accuracy is a function of scale, and saying so is more
    useful than picking an intent count where the number looks good.
    """
    for kind in ("benefit_friction", "channel_timeout", "mixed_failure"):
        events, ground_truth = generate_scenario(
            ScenarioConfig(kind=kind, seed=42, num_intents=5000)
        )
        ref = write_dataset(events, tmp_path, kind)
        result = source.get_funnel(FunnelQuery(dataset_ref=ref.path))
        attributed = sum(d.estimated_lost_intents for d in result.deltas)

        expected = ground_truth.expected_lost_intents
        assert expected > 0
        relative_error = abs(attributed - expected) / expected
        assert relative_error < 0.35, (
            f"{kind}: attributed {attributed} vs injected {expected} "
            f"({relative_error:.0%} error)"
        )


def test_anomalous_stage_carries_the_loss_for_a_single_fault(source, datasets):
    """The stage whose transition broke should carry essentially all the loss."""
    channel = source.get_funnel(FunnelQuery(dataset_ref=datasets["channel_timeout"].path))
    by_stage = {d.stage: d.estimated_lost_intents for d in channel.deltas}
    assert "CHANNEL_SUCCEEDED" in channel.anomalous_stages
    assert by_stage["CHANNEL_SUCCEEDED"] > 0
    # The loss belongs to the transition into the channel stage, not to stages
    # downstream of it that the same intents never reached.
    assert by_stage["CHANNEL_SUCCEEDED"] >= by_stage["PAYMENT_COMPLETED"]
