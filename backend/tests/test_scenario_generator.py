"""Tests for the scenario generator, Ground Truth isolation, and Parquet IO."""

import hashlib

import pytest

from app.domain.events import (
    FUNNEL_STAGE_ORDER,
    EventType,
    FunnelStage,
    Period,
)
from app.harness.scenarios.generator import ScenarioConfig, generate_scenario
from app.harness.scenarios.ground_truth import (
    GENERATOR_VERSION,
    SCENARIO_KINDS,
    GroundTruthLoader,
)
from app.harness.scenarios.io import read_dataset, write_dataset

_SMALL = dict(seed=42, num_intents=300)


def _digest(events, gt) -> str:
    h = hashlib.sha256()
    for e in events:
        h.update(e.model_dump_json().encode())
    h.update(gt.model_dump_json().encode())
    return h.hexdigest()


def test_all_five_kinds_generate():
    for kind in SCENARIO_KINDS:
        events, gt = generate_scenario(ScenarioConfig(kind=kind, **_SMALL))
        assert events, kind
        assert gt.scenario_id == kind
        assert gt.generator_version == GENERATOR_VERSION
        assert gt.random_seed == 42
        periods = {e.period for e in events}
        assert periods == {Period.BASELINE, Period.INCIDENT}


def test_generation_is_reproducible():
    cfg = ScenarioConfig(kind="mixed_failure", **_SMALL)
    e1, g1 = generate_scenario(cfg)
    e2, g2 = generate_scenario(cfg)
    assert _digest(e1, g1) == _digest(e2, g2)


def test_different_seed_differs():
    e1, _ = generate_scenario(ScenarioConfig(kind="normal", seed=1, num_intents=100))
    e2, _ = generate_scenario(ScenarioConfig(kind="normal", seed=2, num_intents=100))
    assert [e.event_id for e in e1] != [e.event_id for e in e2] or _digest(e1, None) != _digest(
        e2, None
    )


def test_baseline_period_is_clean_for_fault_kinds():
    """Baseline period must never contain injected fault events."""
    for kind in ("benefit_friction", "channel_timeout", "mixed_failure"):
        events, _ = generate_scenario(ScenarioConfig(kind=kind, **_SMALL))
        baseline = [e for e in events if e.period == Period.BASELINE]
        fault_types = {
            EventType.ORDER_CANCELLED,
            EventType.PAYMENT_METHOD_SWITCHED,
            EventType.PAYMENT_TIMEOUT,
        }
        assert not {e.event_type for e in baseline} & fault_types, kind


def test_benefit_friction_injects_cancel_and_switch():
    events, gt = generate_scenario(ScenarioConfig(kind="benefit_friction", **_SMALL))
    incident = [e for e in events if e.period == Period.INCIDENT]
    types = {e.event_type for e in incident}
    assert EventType.ORDER_CANCELLED in types
    assert EventType.PAYMENT_METHOD_SWITCHED in types
    assert gt.expected_root_causes == ["BENEFIT_SELECTION_FRICTION"]
    assert gt.injected_parameters.benefit_gap_shift_minor > 0


def test_channel_timeout_only_on_injected_channel():
    events, gt = generate_scenario(ScenarioConfig(kind="channel_timeout", **_SMALL))
    timeouts = [e for e in events if e.event_type == EventType.PAYMENT_TIMEOUT]
    assert timeouts, "expected timeout events"
    assert all(e.payment_channel == "channel_b" for e in timeouts)
    assert all(e.error_code == "CHANNEL_TIMEOUT" for e in timeouts)
    assert gt.affected_dimensions == {"payment_channel": ["channel_b"]}


def test_mixed_failure_has_both_signatures():
    events, gt = generate_scenario(ScenarioConfig(kind="mixed_failure", **_SMALL))
    incident = [e for e in events if e.period == Period.INCIDENT]
    types = {e.event_type for e in incident}
    assert EventType.ORDER_CANCELLED in types
    assert EventType.PAYMENT_TIMEOUT in types
    assert set(gt.expected_root_causes) == {"BENEFIT_SELECTION_FRICTION", "CHANNEL_TIMEOUT"}
    assert set(gt.expected_anomalous_stages) == {
        FunnelStage.PAYMENT_METHOD_SELECTED.value,
        FunnelStage.CHANNEL_SUCCEEDED.value,
    }


def test_data_gap_drops_stages_and_nulls_benefit():
    events, gt = generate_scenario(ScenarioConfig(kind="data_gap", **_SMALL))
    incident = [e for e in events if e.period == Period.INCIDENT]
    stages = {e.funnel_stage for e in incident if e.funnel_stage is not None}
    assert FunnelStage.AUTHENTICATION_PASSED not in stages
    assert FunnelStage.CHANNEL_SUCCEEDED not in stages
    null_rate = sum(1 for e in incident if e.benefit_id is None) / len(incident)
    assert null_rate > 0.5  # baseline is ~0.3; injected rate is 0.85
    assert set(gt.expected_data_gaps) == {
        FunnelStage.AUTHENTICATION_PASSED.value,
        FunnelStage.CHANNEL_SUCCEEDED.value,
        "benefit_id",
    }
    assert gt.expected_root_causes == ["DATA_QUALITY_ISSUE"]


def test_event_ids_unique_per_scenario():
    events, _ = generate_scenario(ScenarioConfig(kind="mixed_failure", **_SMALL))
    ids = [e.event_id for e in events]
    assert len(ids) == len(set(ids))


def test_funnel_stage_order_respected():
    events, _ = generate_scenario(ScenarioConfig(kind="normal", **_SMALL))
    by_intent: dict[str, list] = {}
    for e in events:
        if e.funnel_stage is not None:
            by_intent.setdefault(e.purchase_intent_id, []).append(e.funnel_stage)
    order_idx = {s: i for i, s in enumerate(FUNNEL_STAGE_ORDER)}
    for intent_id, stages in by_intent.items():
        idxs = [order_idx[s] for s in stages]
        assert idxs == sorted(idxs), intent_id


def test_ground_truth_loader_roundtrip_and_isolation(tmp_path):
    _, gt = generate_scenario(ScenarioConfig(kind="normal", **_SMALL))
    loader = GroundTruthLoader(tmp_path / "gt")
    loader.save(gt)
    loaded = loader.load("normal")
    assert loaded == gt
    # Path traversal rejected.
    with pytest.raises(ValueError, match="invalid scenario_id"):
        loader.load("../escape")


def test_dataset_io_roundtrip(tmp_path):
    events, _ = generate_scenario(ScenarioConfig(kind="normal", **_SMALL))
    ref = write_dataset(events, tmp_path, "normal")
    assert ref.num_events == len(events)
    loaded = read_dataset(ref)
    assert loaded == events


def test_dataset_io_detects_tamper(tmp_path):
    events, _ = generate_scenario(ScenarioConfig(kind="normal", **_SMALL))
    ref = write_dataset(events, tmp_path, "normal")
    # Corrupt the parquet file after the ref was created.
    with open(ref.path, "r+b") as fh:
        fh.seek(10)
        fh.write(b"\xff" * 8)
    with pytest.raises(ValueError, match="checksum mismatch"):
        read_dataset(ref)


def test_dataset_ref_never_points_at_ground_truth(tmp_path):
    """DatasetRef schema has no field that could carry Ground Truth content."""
    from app.harness.scenarios.io import DatasetRef

    assert "ground_truth" not in DatasetRef.model_fields
    assert "injected_parameters" not in DatasetRef.model_fields
    events, _ = generate_scenario(ScenarioConfig(kind="normal", **_SMALL))
    ref = write_dataset(events, tmp_path, "normal")
    assert ref.path.endswith(".parquet")


def test_generate_config_changes_mixed_failure():
    from app.harness.scenarios.generator import generate_config_changes

    changes = generate_config_changes("mixed_failure", seed=42)
    assert len(changes) == 2
    types = {c["change_type"] for c in changes}
    assert types == {"promo_rule", "routing"}


def test_generate_config_changes_normal_empty():
    from app.harness.scenarios.generator import generate_config_changes

    changes = generate_config_changes("normal", seed=42)
    assert changes == []


def test_generate_config_changes_channel_timeout():
    from app.harness.scenarios.generator import generate_config_changes

    changes = generate_config_changes("channel_timeout", seed=42)
    assert len(changes) == 1
    assert changes[0]["change_type"] == "routing"
    assert changes[0]["target"] == "channel_b"


def test_generate_config_changes_is_reproducible():
    from app.harness.scenarios.generator import generate_config_changes

    c1 = generate_config_changes("mixed_failure", seed=99)
    c2 = generate_config_changes("mixed_failure", seed=99)
    assert c1 == c2


# --- adversarial scenarios --------------------------------------------------------


def test_adversarial_irrelevant_config_is_clean():
    """adversarial_irrelevant_config: no faults injected, data is clean like normal."""
    events, gt = generate_scenario(ScenarioConfig(kind="adversarial_irrelevant_config", **_SMALL))
    incident = [e for e in events if e.period == Period.INCIDENT]
    fault_types = {
        EventType.ORDER_CANCELLED,
        EventType.PAYMENT_METHOD_SWITCHED,
        EventType.PAYMENT_TIMEOUT,
    }
    assert not {e.event_type for e in incident} & fault_types
    assert gt.expected_root_causes == ["NORMAL_PAYMENT_FAILURE"]
    assert gt.expected_anomalous_stages == []


def test_adversarial_noise_is_clean():
    """adversarial_noise: no faults injected, data is clean like normal."""
    events, gt = generate_scenario(ScenarioConfig(kind="adversarial_noise", **_SMALL))
    assert events
    assert gt.expected_root_causes == ["NORMAL_PAYMENT_FAILURE"]
    assert gt.expected_anomalous_stages == []


def test_adversarial_irrelevant_config_has_config_changes():
    """adversarial_irrelevant_config must have a version_upgrade change."""
    from app.harness.scenarios.generator import generate_config_changes

    changes = generate_config_changes("adversarial_irrelevant_config", seed=42)
    assert len(changes) == 1
    assert changes[0]["change_type"] == "version_upgrade"
    assert "client_ui" in changes[0]["target"]


def test_adversarial_noise_has_no_config_changes():
    """adversarial_noise has no config changes."""
    from app.harness.scenarios.generator import generate_config_changes

    changes = generate_config_changes("adversarial_noise", seed=42)
    assert changes == []
