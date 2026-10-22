"""Evidence contract tests: support status, downgrade, and loss rebalancing.

The product claim under test is "no root cause is published without evidence
that can carry it". These tests exercise the rule directly
(``resolve_support_status``) and through the orchestrator, where the downgrade
must also move the claim's loss out of ``explained``.
"""

import json
from collections.abc import Callable

import pytest

from app.analytics.duckdb_source import DuckDBAnalyticsSource
from app.diagnosis.model import DiagnosisContext
from app.diagnosis.orchestrator import DiagnosisOrchestrator
from app.diagnosis.report import DiagnosisReport, RootCause
from app.diagnosis.validator import ReportValidator, resolve_support_status
from app.harness.scenarios.generator import (
    ScenarioConfig,
    generate_config_changes,
    generate_scenario,
)
from app.harness.scenarios.io import write_dataset
from app.ontology.registry import ONTOLOGY_VERSION, EvidenceType
from app.tools.base import Evidence

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _evidence(code: str, ev_type: EvidenceType) -> Evidence:
    return Evidence(
        evidence_code=code,
        evidence_type=ev_type,
        summary=f"{code} summary",
        metrics={},
        dimensions={},
        tool_name="test_tool",
        tool_call_id="c0",
    )


@pytest.fixture()
def run_evidence() -> dict[str, Evidence]:
    return {
        "EV-001": _evidence("EV-001", EvidenceType.FUNNEL_BASELINE_STABLE),
        "EV-002": _evidence("EV-002", EvidenceType.FUNNEL_STAGE_DEGRADATION),
        "EV-003": _evidence("EV-003", EvidenceType.CHANNEL_TIMEOUT),
        "EV-004": _evidence("EV-004", EvidenceType.CHANNEL_TIMEOUT),
        "EV-005": _evidence("EV-005", EvidenceType.BENEFIT_GAP_FRICTION),
        "EV-006": _evidence("EV-006", EvidenceType.DATA_GAP),
        "EV-007": _evidence("EV-007", EvidenceType.DIMENSION_CONTRIBUTION),
    }


@pytest.fixture(scope="module")
def source():
    return DuckDBAnalyticsSource()


@pytest.fixture(scope="module")
def normal_dataset(tmp_path_factory):
    root = tmp_path_factory.mktemp("contract-datasets")
    events, _ = generate_scenario(ScenarioConfig(kind="normal", seed=42, num_intents=400))
    ref = write_dataset(events, root, "normal")
    (root / "normal.config_changes.json").write_text(
        json.dumps(generate_config_changes("normal", seed=42)), encoding="utf-8"
    )
    return ref


# ---------------------------------------------------------------------------
# resolve_support_status — the contract itself
# ---------------------------------------------------------------------------


def test_no_valid_codes_is_unknown(run_evidence):
    status, reason = resolve_support_status("CHANNEL_TIMEOUT", [], run_evidence)
    assert status == "UNKNOWN"
    assert "no valid evidence" in reason


def test_codes_absent_from_run_are_unknown(run_evidence):
    status, reason = resolve_support_status("CHANNEL_TIMEOUT", ["EV-999"], run_evidence)
    assert status == "UNKNOWN"
    assert "no valid evidence" in reason


def test_negative_evidence_cannot_carry_a_fault_label(run_evidence):
    status, reason = resolve_support_status("CHANNEL_TIMEOUT", ["EV-001"], run_evidence)
    assert status == "UNKNOWN"
    assert "negative evidence" in reason


def test_generic_evidence_alone_cannot_carry_a_specific_fault(run_evidence):
    """A degraded funnel stage is directional, not attributable."""
    status, reason = resolve_support_status("CHANNEL_TIMEOUT", ["EV-002", "EV-007"], run_evidence)
    assert status == "UNKNOWN"
    assert "required evidence" in reason


def test_specific_evidence_supports_the_label(run_evidence):
    status, reason = resolve_support_status("CHANNEL_TIMEOUT", ["EV-003", "EV-002"], run_evidence)
    assert status == "SUPPORTED"
    assert reason is None


def test_observational_evidence_is_only_partial(run_evidence):
    """Benefit gap is friction evidence, never sole causal proof (plan § 13.3)."""
    status, reason = resolve_support_status(
        "BENEFIT_SELECTION_FRICTION", ["EV-005", "EV-002"], run_evidence
    )
    assert status == "PARTIAL"
    assert reason is None


def test_normal_failure_is_supported_by_negative_evidence(run_evidence):
    status, reason = resolve_support_status("NORMAL_PAYMENT_FAILURE", ["EV-001"], run_evidence)
    assert status == "SUPPORTED"
    assert reason is None


def test_data_quality_issue_requires_a_data_gap(run_evidence):
    assert resolve_support_status("DATA_QUALITY_ISSUE", ["EV-001"], run_evidence)[0] == "UNKNOWN"
    assert resolve_support_status("DATA_QUALITY_ISSUE", ["EV-006"], run_evidence)[0] == "SUPPORTED"


def test_unknown_label_needs_no_evidence(run_evidence):
    status, reason = resolve_support_status("UNKNOWN", [], run_evidence)
    assert status == "SUPPORTED"
    assert reason is None


def test_no_anomaly_claim_cannot_contradict_positive_evidence(run_evidence):
    """Claiming "nothing is wrong" while a fault signal is on the table is itself
    an unsupported claim."""
    status, reason = resolve_support_status(
        "NORMAL_PAYMENT_FAILURE", ["EV-001", "EV-003"], run_evidence
    )
    assert status == "UNKNOWN"
    assert "contradicts positive evidence" in reason


# ---------------------------------------------------------------------------
# Validator rules R8 / R10 / R14 / R15
# ---------------------------------------------------------------------------


def _context(evidence: list[Evidence]) -> DiagnosisContext:
    return DiagnosisContext(
        incident_id="inc-1",
        diagnosis_run_id="run-1",
        ontology_version=ONTOLOGY_VERSION,
        evidence_list=evidence,
    )


def _report(causes: list[RootCause], **overrides) -> DiagnosisReport:
    payload = {
        "incident_id": "inc-1",
        "diagnosis_run_id": "run-1",
        "status": "SUCCEEDED",
        "summary": "summary",
        "root_causes": causes,
        "ontology_version": ONTOLOGY_VERSION,
        "validator_version": "paytrace.validator.v1",
    }
    payload.update(overrides)
    return DiagnosisReport(**payload)


def test_r8_rejects_negative_evidence_for_a_fault_label():
    ctx = _context([_evidence("EV-001", EvidenceType.FUNNEL_BASELINE_STABLE)])
    report = _report(
        [
            RootCause(
                label="CHANNEL_TIMEOUT",
                confidence="HIGH",
                explanation="x",
                evidence_codes=["EV-001"],
                rank=1,
            )
        ]
    )
    codes = {i.code for i in ReportValidator().validate(report, ctx)}
    assert "R8_EVIDENCE_LABEL_MISMATCH" in codes


def test_r10_negative_evidence_does_not_license_high_confidence():
    ctx = _context([_evidence("EV-001", EvidenceType.FUNNEL_BASELINE_STABLE)])
    report = _report(
        [
            RootCause(
                label="AUTHENTICATION_FAILURE",
                confidence="HIGH",
                explanation="x",
                evidence_codes=["EV-001"],
                rank=1,
            )
        ]
    )
    codes = {i.code for i in ReportValidator().validate(report, ctx)}
    assert "R10_HIGH_CONF_NO_EV" in codes


def test_r14_flags_a_claim_the_evidence_cannot_carry():
    ctx = _context([_evidence("EV-001", EvidenceType.FUNNEL_BASELINE_STABLE)])
    report = _report(
        [
            RootCause(
                label="CHANNEL_TIMEOUT",
                confidence="HIGH",
                explanation="x",
                evidence_codes=["EV-001"],
                rank=1,
                support_status="SUPPORTED",
            )
        ]
    )
    issues = [
        i for i in ReportValidator().validate(report, ctx) if i.code == "R14_UNSUPPORTED_STATUS"
    ]
    assert len(issues) == 1
    assert "SUPPORTED" in issues[0].message


def test_r15_blocks_explaining_loss_with_an_unknown_claim():
    ctx = _context([_evidence("EV-001", EvidenceType.FUNNEL_BASELINE_STABLE)])
    report = _report(
        [
            RootCause(
                label="CHANNEL_TIMEOUT",
                confidence="LOW",
                explanation="x",
                evidence_codes=["EV-001"],
                rank=1,
                estimated_lost_intents=30,
                support_status="UNKNOWN",
            )
        ],
        total_estimated_lost_intents=50,
        explained_lost_intents=50,
        unexplained_lost_intents=0,
    )
    codes = {i.code for i in ReportValidator().validate(report, ctx)}
    assert "R15_UNKNOWN_EXPLAINS_LOSS" in codes


# ---------------------------------------------------------------------------
# Orchestrator: the downgrade is applied, not merely warned about
# ---------------------------------------------------------------------------


class _StubAdapter:
    """Returns a prepared report so a specific contract violation can be forced.

    Accepts either a fixed report or a factory taking the built context, so a
    test can cite evidence codes that actually exist in the run.
    """

    def __init__(
        self, report: DiagnosisReport | Callable[[DiagnosisContext], DiagnosisReport]
    ) -> None:
        self._source = report

    def generate(self, context: DiagnosisContext) -> DiagnosisReport:
        staged = self._source(context) if callable(self._source) else self._source
        return staged.model_copy(
            update={
                "incident_id": context.incident_id,
                "diagnosis_run_id": context.diagnosis_run_id,
            }
        )


def test_normal_scenario_binds_the_no_anomaly_claim_to_evidence(source, normal_dataset):
    """The one claim that used to be evidence-free now cites system evidence."""
    orchestrator = DiagnosisOrchestrator(source=source, artifacts=None)
    report = orchestrator.run(dataset_ref=str(normal_dataset.path), scenario_id="normal")

    assert len(report.root_causes) == 1
    rc = report.root_causes[0]
    assert rc.label == "NORMAL_PAYMENT_FAILURE"
    assert rc.evidence_codes, "no-anomaly claim must cite the baseline-stable evidence"
    assert rc.support_status == "SUPPORTED"


def test_unsupported_claim_is_downgraded_and_its_loss_becomes_unexplained(source, normal_dataset):
    """End-to-end: total 40, one UNKNOWN claim of 40 → explained 0, unexplained 40."""
    staged = _report(
        [
            RootCause(
                label="CHANNEL_TIMEOUT",
                confidence="LOW",
                explanation="staged unsupported claim",
                evidence_codes=["EV-DOES-NOT-EXIST"],
                rank=1,
                estimated_lost_intents=40,
                support_status="SUPPORTED",
            )
        ],
        total_estimated_lost_intents=40,
        explained_lost_intents=40,
        unexplained_lost_intents=0,
    )
    orchestrator = DiagnosisOrchestrator(
        source=source, artifacts=None, adapter=_StubAdapter(staged)
    )
    execution = orchestrator.run_detailed(
        dataset_ref=str(normal_dataset.path), scenario_id="normal"
    )
    report = execution.report

    assert report.root_causes[0].support_status == "UNKNOWN"
    assert report.explained_lost_intents == 0
    assert report.unexplained_lost_intents == report.total_estimated_lost_intents

    downgrades = [i for i in execution.validation_issues if i.code == "R14_UNSUPPORTED_STATUS"]
    assert len(downgrades) == 1, "the downgrade must be recorded in the trace, not silent"
    assert "SUPPORTED -> UNKNOWN" in downgrades[0].message


def test_supported_claim_keeps_its_share_of_explained_loss(source, normal_dataset):
    """The rebalance must not zero out loss that IS backed by evidence."""

    def staged(context: DiagnosisContext) -> DiagnosisReport:
        codes = [e.evidence_code for e in context.evidence_list]
        assert codes, "the normal scenario must produce baseline-stable evidence"
        return _report(
            [
                RootCause(
                    label="NORMAL_PAYMENT_FAILURE",
                    confidence="LOW",
                    explanation="supported by negative evidence",
                    evidence_codes=codes,
                    rank=1,
                    estimated_lost_intents=0,
                    support_status="SUPPORTED",
                )
            ],
            total_estimated_lost_intents=25,
            explained_lost_intents=25,
            unexplained_lost_intents=0,
        )

    orchestrator = DiagnosisOrchestrator(
        source=source, artifacts=None, adapter=_StubAdapter(staged)
    )
    report = orchestrator.run(dataset_ref=str(normal_dataset.path), scenario_id="normal")

    # NORMAL_PAYMENT_FAILURE claims 0 lost intents, so nothing is explained.
    assert report.root_causes[0].support_status == "SUPPORTED"
    assert report.explained_lost_intents == 0
    assert report.unexplained_lost_intents == 25
