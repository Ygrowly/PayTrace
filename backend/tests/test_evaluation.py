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
    assert first.markdown_bytes.startswith(b"# PayTrace Rule-based Evaluation Report")


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
