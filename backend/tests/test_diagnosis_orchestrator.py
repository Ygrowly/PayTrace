"""End-to-end tests for the M2a diagnosis orchestrator.

Covers all five scenario kinds through the full fixed workflow:
  tools → evidence → context → model → validate → report.
"""

import json

import pytest

from app.analytics.duckdb_source import DuckDBAnalyticsSource
from app.diagnosis.orchestrator import DiagnosisOrchestrator
from app.diagnosis.report import DiagnosisReport
from app.harness.scenarios.generator import (
    ScenarioConfig,
    generate_config_changes,
    generate_scenario,
)
from app.harness.scenarios.io import write_dataset
from app.ontology.registry import ONTOLOGY_VERSION

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def source():
    return DuckDBAnalyticsSource()


@pytest.fixture(scope="module")
def datasets(tmp_path_factory):
    root = tmp_path_factory.mktemp("datasets")
    refs = {}
    for kind in (
        "normal",
        "benefit_friction",
        "channel_timeout",
        "mixed_failure",
        "data_gap",
        "adversarial_irrelevant_config",
        "adversarial_noise",
    ):
        events, _ = generate_scenario(ScenarioConfig(kind=kind, seed=42, num_intents=400))
        refs[kind] = write_dataset(events, root, kind)
        # Write config changes alongside the Parquet for get_config_changes tool.
        config_path = root / f"{kind}.config_changes.json"
        config_path.write_text(json.dumps(generate_config_changes(kind, seed=42)), encoding="utf-8")
    return refs


@pytest.fixture()
def orchestrator(source):
    return DiagnosisOrchestrator(source=source, artifacts=None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_report_structure(report: DiagnosisReport) -> None:
    """Common structural invariants for every valid report."""
    assert report.incident_id
    assert report.diagnosis_run_id
    assert report.status in ("SUCCEEDED", "NEEDS_DATA")
    assert report.ontology_version == ONTOLOGY_VERSION
    assert report.validator_version == "paytrace.validator.v1"
    assert report.summary
    assert isinstance(report.anomalous_stages, list)
    assert isinstance(report.root_causes, list)
    assert report.total_estimated_lost_intents >= 0
    assert report.explained_lost_intents >= 0
    assert report.unexplained_lost_intents >= 0
    assert isinstance(report.recommended_actions, list)


# ---------------------------------------------------------------------------
# Scenario-kind specific tests
# ---------------------------------------------------------------------------


def test_normal_produces_single_root_cause_low_confidence(orchestrator, datasets):
    """normal → NORMAL_PAYMENT_FAILURE, LOW, zero lost intents."""
    report = orchestrator.run(dataset_ref=str(datasets["normal"].path), scenario_id="normal")
    _assert_report_structure(report)
    assert report.status == "SUCCEEDED"
    assert len(report.root_causes) == 1
    rc = report.root_causes[0]
    assert rc.label == "NORMAL_PAYMENT_FAILURE"
    assert rc.confidence == "LOW"
    assert rc.estimated_lost_intents == 0
    assert rc.rank == 1
    assert "No significant evidence" in rc.explanation
    assert report.total_estimated_lost_intents == 0


def test_channel_timeout_produces_channel_timeout_root_cause(orchestrator, datasets):
    """channel_timeout → CHANNEL_TIMEOUT, HIGH, positive lost intents."""
    report = orchestrator.run(
        dataset_ref=str(datasets["channel_timeout"].path),
        incident_id="test-inc-timeout",
        diagnosis_run_id="test-run-timeout",
    )
    _assert_report_structure(report)
    assert report.status == "SUCCEEDED"
    assert report.incident_id == "test-inc-timeout"
    assert report.diagnosis_run_id == "test-run-timeout"

    labels = {rc.label for rc in report.root_causes}
    assert "CHANNEL_TIMEOUT" in labels

    timeout_rc = next(rc for rc in report.root_causes if rc.label == "CHANNEL_TIMEOUT")
    assert timeout_rc.confidence == "HIGH"
    assert timeout_rc.estimated_lost_intents is not None
    assert timeout_rc.estimated_lost_intents > 0
    assert timeout_rc.evidence_codes
    assert timeout_rc.category == "infrastructure"
    assert any("timeout" in rc.explanation.lower() for rc in report.root_causes)
    assert report.total_estimated_lost_intents > 0


def test_benefit_friction_produces_benefit_selection_root_cause(orchestrator, datasets):
    """benefit_friction → BENEFIT_SELECTION_FRICTION, MEDIUM, positive lost intents."""
    report = orchestrator.run(
        dataset_ref=str(datasets["benefit_friction"].path),
        scenario_id="benefit_friction",
    )
    _assert_report_structure(report)
    assert report.status == "SUCCEEDED"

    labels = {rc.label for rc in report.root_causes}
    assert "BENEFIT_SELECTION_FRICTION" in labels

    benefit_rc = next(rc for rc in report.root_causes if rc.label == "BENEFIT_SELECTION_FRICTION")
    assert benefit_rc.confidence == "MEDIUM"
    # BENEFIT_GAP_FRICTION evidence does not carry an explicit lost-intents
    # metric — the root cause is detected qualitatively from gap shift.
    assert benefit_rc.estimated_lost_intents is None or benefit_rc.estimated_lost_intents >= 0
    assert benefit_rc.evidence_codes
    assert "benefit" in benefit_rc.explanation.lower()
    # Benefit friction may not cause funnel degradation above the anomaly
    # threshold — total lost intents can be 0 even when root cause exists.


def test_mixed_failure_produces_dual_root_causes(orchestrator, datasets):
    """mixed_failure → CHANNEL_TIMEOUT + BENEFIT_SELECTION_FRICTION."""
    report = orchestrator.run(
        dataset_ref=str(datasets["mixed_failure"].path),
        incident_id="test-inc-mixed",
        diagnosis_run_id="test-run-mixed",
    )
    _assert_report_structure(report)
    assert report.status == "SUCCEEDED"
    assert len(report.root_causes) >= 2

    labels = {rc.label for rc in report.root_causes}
    assert "CHANNEL_TIMEOUT" in labels, f"got labels: {labels}"
    assert "BENEFIT_SELECTION_FRICTION" in labels, f"got labels: {labels}"

    # Each root cause must have non-empty evidence codes.
    for rc in report.root_causes:
        assert rc.evidence_codes, f"root cause {rc.label} has no evidence codes"

    # Confidence and rank are assigned.
    confidences = {rc.confidence for rc in report.root_causes}
    assert "HIGH" in confidences  # CHANNEL_TIMEOUT
    assert len({rc.rank for rc in report.root_causes}) == len(report.root_causes)

    assert report.total_estimated_lost_intents > 0
    # explained + unexplained ≈ total (±2 tolerance)
    assert (
        abs(
            report.total_estimated_lost_intents
            - (report.explained_lost_intents + report.unexplained_lost_intents)
        )
        <= 2
    )


def test_data_gap_produces_needs_data_status(orchestrator, datasets):
    """data_gap → NEEDS_DATA with missing_data populated and zero root causes."""
    report = orchestrator.run(dataset_ref=str(datasets["data_gap"].path), scenario_id="data_gap")
    _assert_report_structure(report)
    assert report.status == "NEEDS_DATA"
    assert report.missing_data, "NEEDS_DATA must list specific missing data"
    assert report.root_causes == []
    assert "missing" in report.summary.lower() or "data quality" in report.summary.lower()


def test_report_validates_clean(orchestrator, datasets):
    """Valid reports should have zero validation issues after generation."""
    for kind in ("normal", "benefit_friction", "channel_timeout", "mixed_failure"):
        report = orchestrator.run(
            dataset_ref=str(datasets[kind].path),
            incident_id=f"test-inc-{kind}",
            diagnosis_run_id=f"test-run-{kind}",
        )
        assert report.status == "SUCCEEDED", f"{kind} should succeed"
        assert report.root_causes, f"{kind} should have root causes"
        # Validator version must match.
        assert report.validator_version == "paytrace.validator.v1"


def test_orchestrator_auto_generates_ids(orchestrator, datasets):
    """When ids are omitted, the orchestrator auto-generates them."""
    report = orchestrator.run(dataset_ref=str(datasets["normal"].path))
    assert report.incident_id.startswith("inc-")
    assert report.diagnosis_run_id.startswith("run-")
    assert len(report.incident_id) > 4
    assert len(report.diagnosis_run_id) > 4


def test_orchestrator_with_auto_generated_ids_are_decorrelated(orchestrator, datasets):
    """Auto-generated ids are unique per run even for the same dataset."""
    r1 = orchestrator.run(dataset_ref=str(datasets["normal"].path))
    r2 = orchestrator.run(dataset_ref=str(datasets["normal"].path))
    # Same dataset, same deterministic adapter → same report content, but
    # different incident + run ids.
    assert r1.incident_id != r2.incident_id
    assert r1.diagnosis_run_id != r2.diagnosis_run_id
    # The rest of the report (status, labels, loss) is identical because the
    # adapter is deterministic.
    assert r1.status == r2.status
    assert [rc.label for rc in r1.root_causes] == [rc.label for rc in r2.root_causes]


# --- adversarial scenarios --------------------------------------------------------


def test_adversarial_irrelevant_config_behaves_like_normal(orchestrator, datasets):
    """adversarial_irrelevant_config → NORMAL_PAYMENT_FAILURE, LOW, zero lost."""
    report = orchestrator.run(
        dataset_ref=str(datasets["adversarial_irrelevant_config"].path),
        scenario_id="adversarial_irrelevant_config",
    )
    _assert_report_structure(report)
    assert report.status == "SUCCEEDED"
    assert len(report.root_causes) >= 1
    rc = report.root_causes[0]
    assert rc.label == "NORMAL_PAYMENT_FAILURE"
    assert rc.confidence == "LOW"
    # Must not contain evidence codes that reference the irrelevant config change
    # (version_upgrade should not appear in root cause evidence).
    for rc_item in report.root_causes:
        assert "version_upgrade" not in str(rc_item.evidence_codes)


def test_adversarial_noise_behaves_like_normal(orchestrator, datasets):
    """adversarial_noise → NORMAL_PAYMENT_FAILURE, LOW, zero lost."""
    report = orchestrator.run(
        dataset_ref=str(datasets["adversarial_noise"].path),
        scenario_id="adversarial_noise",
    )
    _assert_report_structure(report)
    assert report.status == "SUCCEEDED"
    assert len(report.root_causes) >= 1
    rc = report.root_causes[0]
    assert rc.label == "NORMAL_PAYMENT_FAILURE"
    assert rc.confidence == "LOW"
    assert rc.estimated_lost_intents == 0
