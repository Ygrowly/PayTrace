"""M3 Evaluation Runner and metric coverage."""

from app.diagnosis.orchestrator import DiagnosisExecution
from app.diagnosis.report import DiagnosisReport
from app.evaluation.metrics import score_scenario
from app.evaluation.runner import run_evaluation
from app.harness.artifact_store import LocalArtifactStore
from app.harness.scenarios.generator import ScenarioConfig, generate_scenario
from app.tools.base import EvidenceLedger


def test_data_gap_needs_data_is_not_a_root_cause_miss() -> None:
    _, ground_truth = generate_scenario(ScenarioConfig(kind="data_gap", seed=42, num_intents=20))
    report = DiagnosisReport(
        incident_id="incident",
        diagnosis_run_id="run",
        status="NEEDS_DATA",
        summary="Data quality issues require a complete dataset.",
        anomalous_stages=[],
        root_causes=[],
        missing_data=[
            "missing funnel stages: AUTHENTICATION_PASSED, CHANNEL_SUCCEEDED",
            "high benefit_id null rate: 85.00%",
        ],
        ontology_version="paytrace.ontology.v1",
        validator_version="paytrace.validator.v1",
    )

    result = score_scenario(
        scenario_kind="data_gap",
        report=report,
        ground_truth=ground_truth,
        diagnosis_status="NEEDS_DATA",
    )

    assert result.root_cause_f1 is None
    assert result.badcases == []


def test_rule_based_evaluation_is_reproducible_and_exposes_mixed_failure(tmp_path) -> None:
    kwargs = {
        "scenario_kinds": [
            "normal",
            "benefit_friction",
            "channel_timeout",
            "mixed_failure",
            "data_gap",
        ],
        "seed": 42,
        "num_intents": 300,
    }
    first = run_evaluation(
        evaluation_run_id="eval-reproducible",
        scenario_root=tmp_path / "first" / "scenarios",
        artifacts=LocalArtifactStore(tmp_path / "first" / "artifacts"),
        **kwargs,
    )
    second = run_evaluation(
        evaluation_run_id="eval-reproducible",
        scenario_root=tmp_path / "second" / "scenarios",
        artifacts=LocalArtifactStore(tmp_path / "second" / "artifacts"),
        **kwargs,
    )

    def core(report):
        return [
            (
                item.scenario_kind,
                item.diagnosis_status,
                item.predicted_anomalous_stages,
                item.expected_anomalous_stages,
                item.predicted_root_causes,
                item.expected_root_causes,
                item.predicted_missing_data,
                item.expected_data_gaps,
                item.badcases,
            )
            for item in report.scenario_results
        ]

    assert core(first.report) == core(second.report)
    assert first.report.metrics.scenario_count == 5
    mixed = next(
        item for item in first.report.scenario_results if item.scenario_kind == "mixed_failure"
    )
    assert set(mixed.predicted_root_causes) == {
        "BENEFIT_SELECTION_FRICTION",
        "CHANNEL_TIMEOUT",
    }
    assert mixed.evidence
    assert mixed.tool_trace
    assert "ground_truth" not in first.json_bytes.decode("utf-8")
    assert first.markdown_bytes.startswith(b"# PayTrace Evaluation Report")


def test_ground_truth_is_loaded_after_diagnosis(monkeypatch, tmp_path) -> None:
    _, ground_truth = generate_scenario(ScenarioConfig(kind="normal", seed=42, num_intents=20))
    order: list[str] = []

    class RecordingGroundTruthLoader:
        def __init__(self, root) -> None:  # noqa: ANN001
            self.root = root

        def save(self, value) -> None:  # noqa: ANN001
            del value

        def load(self, kind):  # noqa: ANN001
            order.append(f"ground_truth:{kind}")
            return ground_truth

    class RecordingOrchestrator:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            del kwargs

        def run_detailed(self, *args, **kwargs):  # noqa: ANN002, ANN003
            del args, kwargs
            assert order == []
            order.append("diagnosis")
            return DiagnosisExecution(
                report=DiagnosisReport(
                    incident_id="incident",
                    diagnosis_run_id="run",
                    status="SUCCEEDED",
                    summary="No anomaly",
                    ontology_version="paytrace.ontology.v1",
                    validator_version="paytrace.validator.v1",
                ),
                ledger=EvidenceLedger(),
                tool_results=(),
                validation_issues=(),
            )

    monkeypatch.setattr("app.evaluation.runner.GroundTruthLoader", RecordingGroundTruthLoader)
    monkeypatch.setattr("app.evaluation.runner.DiagnosisOrchestrator", RecordingOrchestrator)

    run_evaluation(
        evaluation_run_id="eval-order",
        scenario_kinds=["normal"],
        num_intents=20,
        scenario_root=tmp_path / "scenarios",
        artifacts=LocalArtifactStore(tmp_path / "artifacts"),
    )

    assert order == ["diagnosis", "ground_truth:normal"]


# --- B1 model mode ----------------------------------------------------------------


def test_b1_mode_falls_back_to_rule_based_when_no_api_key(monkeypatch, tmp_path) -> None:
    """B1 with no API key must fall back to RuleBasedModelAdapter and succeed.

    The test forces empty credentials via monkeypatch so that the fallback
    path is exercised deterministically, regardless of what .env contains.
    Without this, a real MODEL_API_KEY in .env would make B1 actually call
    the LLM, producing non-deterministic results and violating the rule
    that tests must not call paid external services.
    """

    class _EmptyModelSettings:
        model_base_url = ""
        model_api_key = ""
        model_name = ""

    monkeypatch.setattr("app.evaluation.runner.get_settings", lambda: _EmptyModelSettings())

    result = run_evaluation(
        evaluation_run_id="eval-b1-fallback",
        model_mode="B1",
        scenario_kinds=["normal"],
        seed=42,
        num_intents=100,
        scenario_root=tmp_path / "scenarios",
        artifacts=LocalArtifactStore(tmp_path / "artifacts"),
    )
    assert result.report.metrics.run_success_rate == 1.0
    assert result.report.model_mode == "B1"
    normal = next(item for item in result.report.scenario_results if item.scenario_kind == "normal")
    assert normal.diagnosis_status == "SUCCEEDED"
    assert normal.adapter_name == "RuleBasedModelAdapter"
    assert normal.fallback_used is True
    assert normal.fallback_reason == "MODEL_NOT_CONFIGURED"
    assert result.report.metrics.model_invocation_count == 0
    assert result.report.metrics.fallback_count == 1


def test_unknown_model_mode_is_rejected(tmp_path) -> None:
    """A mode outside the B0/B1/B2 ladder must raise ValueError."""
    import pytest

    with pytest.raises(ValueError, match="model_mode must be B0, B1 or B2"):
        run_evaluation(
            evaluation_run_id="eval-bad-mode",
            model_mode="B9",
            scenario_kinds=["normal"],
            num_intents=100,
            scenario_root=tmp_path / "scenarios",
            artifacts=LocalArtifactStore(tmp_path / "artifacts"),
        )


def test_b2_runs_the_investigation_and_records_its_policy(tmp_path) -> None:
    """B2 must be a real harness run, and its policy provenance must be visible.

    With no reachable model the policy falls back to the scripted investigator;
    the run must say so rather than presenting itself as a model investigation.
    """
    result = run_evaluation(
        evaluation_run_id="eval-b2",
        model_mode="B2",
        scenario_kinds=["channel_timeout"],
        num_intents=200,
        scenario_root=tmp_path / "scenarios",
        artifacts=LocalArtifactStore(tmp_path / "artifacts"),
    )
    scenario = result.report.scenario_results[0]
    assert scenario.agent_mode == "B2"
    assert scenario.policy_name == "OpenAIToolCallingPolicy"
    assert scenario.fallback_used is True
    assert scenario.fallback_reason in ("MODEL_NOT_CONFIGURED", "MODEL_CALL_FAILED")
    assert result.report.metrics.model_invocation_count == 0
    assert result.report.metrics.fallback_count == 1


def test_b0_mode_still_works(tmp_path) -> None:
    """B0 mode must produce the same results as before."""
    result = run_evaluation(
        evaluation_run_id="eval-b0",
        model_mode="B0",
        scenario_kinds=["normal"],
        seed=42,
        num_intents=100,
        scenario_root=tmp_path / "scenarios",
        artifacts=LocalArtifactStore(tmp_path / "artifacts"),
    )
    assert result.report.metrics.run_success_rate == 1.0
    assert result.report.model_mode == "B0"
    assert result.report.metrics.scenario_count == 1
    assert result.report.metrics.model_invocation_count == 0
    assert result.report.metrics.fallback_count == 0


# ---------------------------------------------------------------------------
# Corrected metric definitions (W3)
#
# Each of these used to be tautological or issue-counted, so a green evaluation
# proved nothing. They now measure what their names say.
# ---------------------------------------------------------------------------


def _scored(ground_truth, report, *, evidence=(), tool_results=()):
    return score_scenario(
        scenario_kind=ground_truth.scenario_id,
        report=report,
        ground_truth=ground_truth,
        diagnosis_status=report.status,
        run_evidence=list(evidence),
        tool_results=list(tool_results),
    )


def _evidence(code, ev_type, tool_call_id):
    from app.ontology.registry import EvidenceType
    from app.tools.base import Evidence

    return Evidence(
        evidence_code=code,
        evidence_type=getattr(EvidenceType, ev_type),
        summary=f"{code} summary",
        metrics={},
        dimensions={},
        tool_name="t",
        tool_call_id=tool_call_id,
    )


def _report_with(causes, *, total, explained, unexplained):
    return DiagnosisReport(
        incident_id="incident",
        diagnosis_run_id="run",
        status="SUCCEEDED",
        summary="summary",
        anomalous_stages=["CHANNEL_SUCCEEDED"],
        root_causes=causes,
        total_estimated_lost_intents=total,
        explained_lost_intents=explained,
        unexplained_lost_intents=unexplained,
        ontology_version="paytrace.ontology.v1",
        validator_version="paytrace.validator.v1",
    )


def test_unsupported_claim_rate_counts_claims_not_validation_issues() -> None:
    from app.diagnosis.report import RootCause
    from app.diagnosis.validator import ValidationIssue

    _, gt = generate_scenario(ScenarioConfig(kind="channel_timeout", seed=42, num_intents=50))
    report = _report_with(
        [
            RootCause(
                label="CHANNEL_TIMEOUT",
                confidence="HIGH",
                explanation="supported",
                evidence_codes=["EV-001"],
                rank=1,
                support_status="SUPPORTED",
            ),
            RootCause(
                label="UNKNOWN",
                confidence="LOW",
                explanation="unattributed",
                evidence_codes=[],
                rank=2,
                support_status="UNKNOWN",
            ),
        ],
        total=10,
        explained=10,
        unexplained=0,
    )
    # Two issues on the SAME claim must not make the rate 2/2.
    issues = [
        ValidationIssue("R3_NO_EVIDENCE", "root_causes[1]", "x", retryable=True),
        ValidationIssue("R10_HIGH_CONF_NO_EV", "root_causes[1]", "y", retryable=True),
    ]
    result = score_scenario(
        scenario_kind="channel_timeout",
        report=report,
        ground_truth=gt,
        validation_issues=issues,
        diagnosis_status="SUCCEEDED",
    )
    assert result.unsupported_claim_rate == 0.5
    assert result.validation_issue_codes == ["R10_HIGH_CONF_NO_EV", "R3_NO_EVIDENCE"]


def test_loss_attribution_error_is_measured_against_ground_truth() -> None:
    """A report that is internally consistent but wrong must not score 0."""
    from app.diagnosis.report import RootCause

    _, gt = generate_scenario(ScenarioConfig(kind="channel_timeout", seed=42, num_intents=500))
    assert gt.expected_lost_intents > 0

    report = _report_with(
        [
            RootCause(
                label="CHANNEL_TIMEOUT",
                confidence="HIGH",
                explanation="understated",
                evidence_codes=["EV-001"],
                rank=1,
                estimated_lost_intents=1,
                support_status="SUPPORTED",
            )
        ],
        total=1,
        explained=1,
        unexplained=0,
    )
    result = score_scenario(
        scenario_kind="channel_timeout",
        report=report,
        ground_truth=gt,
        diagnosis_status="SUCCEEDED",
    )
    expected_error = abs(1 - gt.expected_lost_intents) / gt.expected_lost_intents
    assert result.loss_attribution_rel_error == expected_error
    assert result.loss_attribution_rel_error > 0.9
    assert "LOSS_ATTRIBUTION_ERROR" in result.badcases


def test_evidence_from_a_failed_tool_call_is_not_valid() -> None:
    from app.diagnosis.report import RootCause
    from app.tools.base import ToolResult

    _, gt = generate_scenario(ScenarioConfig(kind="channel_timeout", seed=42, num_intents=50))
    report = _report_with(
        [
            RootCause(
                label="CHANNEL_TIMEOUT",
                confidence="HIGH",
                explanation="cites a failed call",
                evidence_codes=["EV-001", "EV-002"],
                rank=1,
                support_status="SUPPORTED",
            )
        ],
        total=5,
        explained=5,
        unexplained=0,
    )
    evidence = [
        _evidence("EV-001", "CHANNEL_TIMEOUT", "c0"),
        _evidence("EV-002", "DIMENSION_CONTRIBUTION", "c1"),
    ]
    tool_results = [
        ToolResult(tool_call_id="c0", tool_name="t", status="success", summary="ok"),
        ToolResult(tool_call_id="c1", tool_name="t", status="partial", summary="truncated"),
    ]
    result = _scored(gt, report, evidence=evidence, tool_results=tool_results)
    assert result.evidence_validity_rate == 0.5
