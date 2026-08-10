"""Deterministic Evaluation Runner for the M3 Eval Lab.

The runner materialises the harness scenarios, runs the same fixed
diagnosis workflow used by M2 with the configured ModelAdapter, and scores the
result only after diagnosis has finished. Ground Truth is loaded here and is
never passed to ``DiagnosisContext`` or a model adapter.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from app.analytics.duckdb_source import DuckDBAnalyticsSource
from app.config import get_settings
from app.diagnosis.adapter import OpenAICompatibleModelAdapter, RuleBasedModelAdapter
from app.diagnosis.orchestrator import DiagnosisExecution, DiagnosisOrchestrator
from app.diagnosis.prompts import PROMPT_VERSION
from app.evaluation.metrics import aggregate, score_scenario
from app.evaluation.models import EvaluationReport, ScenarioResult
from app.harness.artifact_store import ArtifactStore
from app.harness.scenarios.generator import (
    ScenarioConfig,
    generate_config_changes,
    generate_scenario,
)
from app.harness.scenarios.ground_truth import (
    GENERATOR_VERSION,
    SCENARIO_KINDS,
    GroundTruthLoader,
)
from app.harness.scenarios.io import write_dataset
from app.ontology.registry import ONTOLOGY_VERSION

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCENARIO_ROOT = REPO_ROOT / "data" / "scenarios"
logger = logging.getLogger(__name__)


@dataclass
class EvaluationExecution:
    """Evaluation report and the serialized report artifacts."""

    report: EvaluationReport
    json_bytes: bytes
    markdown_bytes: bytes


def resolve_runtime_path(value: str | Path) -> Path:
    """Resolve a configured runtime path relative to the monorepo root."""
    path = Path(value)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def _validate_config(
    *, scenario_kinds: Iterable[str], seed: int, num_intents: int, model_mode: str
) -> list[str]:
    kinds = list(dict.fromkeys(scenario_kinds))
    invalid = sorted(set(kinds) - set(SCENARIO_KINDS))
    if invalid:
        raise ValueError(f"unsupported scenario kinds: {', '.join(invalid)}")
    if not kinds:
        raise ValueError("scenario_kinds must contain at least one scenario")
    if num_intents < 1 or num_intents > 10_000:
        raise ValueError("num_intents must be between 1 and 10000")
    if model_mode not in ("B0", "B1"):
        raise ValueError("model_mode must be B0 or B1")
    # ``seed`` is intentionally not restricted: negative deterministic seeds
    # are valid inputs to Python's random.Random and are useful in experiments.
    _ = seed
    return [str(kind) for kind in kinds]


def _serialize_execution(execution: DiagnosisExecution) -> tuple[list[dict], list[dict]]:
    evidence = [item.model_dump(mode="json") for item in execution.ledger.all()]
    trace = [item.model_dump(mode="json") for item in execution.tool_results]
    return evidence, trace


def _score_one(
    *,
    kind: str,
    dataset_path: Path,
    ground_truth_loader: GroundTruthLoader,
    orchestrator: DiagnosisOrchestrator,
    evaluation_run_id: str,
) -> ScenarioResult:
    started = time.perf_counter()
    execution: DiagnosisExecution | None = None
    try:
        # Do not pass ``kind`` into the diagnosis context. The generated
        # dataset is the only runtime signal available to the workflow.
        execution = orchestrator.run_detailed(
            str(dataset_path),
            incident_id=f"eval-{evaluation_run_id}-{kind}",
            diagnosis_run_id=f"eval-run-{evaluation_run_id}-{kind}",
            scenario_id="",
        )
    except Exception as exc:  # noqa: BLE001 - one bad scenario must be scored as a badcase
        logger.exception("evaluation scenario failed: kind=%s", kind)
        latency_ms = int((time.perf_counter() - started) * 1000)
        ground_truth = ground_truth_loader.load(kind)
        return score_scenario(
            scenario_kind=kind,
            report=None,
            ground_truth=ground_truth,
            diagnosis_status="FAILED",
            latency_ms=latency_ms,
        ).model_copy(
            update={
                "report_summary": f"{type(exc).__name__}: {str(exc)[:500]}",
                "tool_trace": [],
            }
        )

    latency_ms = int((time.perf_counter() - started) * 1000)
    ground_truth = ground_truth_loader.load(kind)
    report = execution.report
    result = score_scenario(
        scenario_kind=kind,
        report=report,
        ground_truth=ground_truth,
        validation_issues=execution.validation_issues,
        diagnosis_status=report.status,
        latency_ms=latency_ms,
    )
    evidence, trace = _serialize_execution(execution)
    return result.model_copy(
        update={
            "report_summary": report.summary,
            "unexplained_lost_intents": report.unexplained_lost_intents,
            "recommended_actions": report.recommended_actions,
            "evidence": evidence,
            "tool_trace": trace,
            "tool_call_count": len(execution.tool_results),
        }
    )


def render_markdown(report: EvaluationReport) -> bytes:
    """Render the evaluation report as a small, portable Markdown artifact."""
    m = report.metrics
    lines = [
        "# PayTrace Rule-based Evaluation Report",
        "",
        f"- Evaluation run: `{report.evaluation_run_id}`",
        f"- Model mode: `{report.model_mode}`",
        f"- Seed: `{report.seed}`",
        f"- Intents per scenario: `{report.num_intents}`",
        f"- Generator: `{report.generator_version}`",
        f"- Ontology: `{report.ontology_version}`",
        "",
        "## Aggregate metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Run success rate | {m.run_success_rate:.2%} |",
        f"| Stage localization exact rate | {m.stage_localization_exact_rate:.2%} |",
        f"| Stage overlap mean | {m.stage_localization_overlap_mean:.3f} |",
        f"| Root-cause F1 mean | {m.root_cause_f1_mean:.3f} |",
        f"| Evidence validity mean | {m.evidence_validity_rate_mean:.2%} |",
        f"| Unsupported-claim rate mean | {m.unsupported_claim_rate_mean:.2%} |",
        f"| Badcase scenarios | {m.badcase_count} |",
        "",
        "## Scenario results",
        "",
        "| Scenario | Status | Predicted root causes | Expected root causes | Badcases |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in report.scenario_results:
        lines.append(
            "| {scenario} | {status} | {predicted} | {expected} | {badcases} |".format(
                scenario=result.scenario_kind,
                status=result.diagnosis_status,
                predicted=", ".join(result.predicted_root_causes) or "—",
                expected=", ".join(result.expected_root_causes) or "—",
                badcases=", ".join(result.badcases) or "—",
            )
        )

    if report.badcases:
        lines.extend(["", "## Badcases", ""])
        for badcase in report.badcases:
            lines.append(
                "- **{scenario_kind}**: {categories}".format(
                    scenario_kind=badcase["scenario_kind"],
                    categories=", ".join(badcase["categories"]),
                )
            )

    return ("\n".join(lines) + "\n").encode("utf-8")


def run_evaluation(
    *,
    evaluation_run_id: str,
    model_mode: str = "B0",
    prompt_version: str | None = None,
    scenario_kinds: Iterable[str] = SCENARIO_KINDS,
    seed: int = 42,
    num_intents: int = 5000,
    scenario_root: str | Path = DEFAULT_SCENARIO_ROOT,
    artifacts: ArtifactStore | None = None,
) -> EvaluationExecution:
    """Run a deterministic batch and return JSON/Markdown report bytes."""
    kinds = _validate_config(
        scenario_kinds=scenario_kinds,
        seed=seed,
        num_intents=num_intents,
        model_mode=model_mode,
    )
    root = resolve_runtime_path(scenario_root)
    events_root = root / "events"
    ground_truth_loader = GroundTruthLoader(root / "ground_truth")

    if model_mode == "B1":
        settings = get_settings()
        adapter = OpenAICompatibleModelAdapter(
            base_url=settings.model_base_url,
            api_key=settings.model_api_key,
            model=settings.model_name,
            prompt_version=prompt_version or PROMPT_VERSION,
        )
    else:
        adapter = RuleBasedModelAdapter()

    orchestrator = DiagnosisOrchestrator(
        source=DuckDBAnalyticsSource(), artifacts=artifacts, adapter=adapter
    )
    results: list[ScenarioResult] = []

    for kind in kinds:
        events, ground_truth = generate_scenario(
            ScenarioConfig(kind=kind, seed=seed, num_intents=num_intents)
        )
        dataset_ref = write_dataset(events, events_root, kind)
        ground_truth_loader.save(ground_truth)
        # Write config changes alongside the Parquet for get_config_changes tool.
        config_path = events_root / f"{dataset_ref.scenario_id}.config_changes.json"
        config_path.write_text(json.dumps(generate_config_changes(kind, seed)), encoding="utf-8")
        results.append(
            _score_one(
                kind=kind,
                dataset_path=Path(dataset_ref.path),
                ground_truth_loader=ground_truth_loader,
                orchestrator=orchestrator,
                evaluation_run_id=evaluation_run_id,
            )
        )

    metrics = aggregate(results)
    report = EvaluationReport(
        evaluation_run_id=evaluation_run_id,
        model_mode=model_mode,
        prompt_version=prompt_version,
        seed=seed,
        num_intents=num_intents,
        metrics=metrics,
        scenario_results=results,
        badcases=[
            {
                "scenario_kind": result.scenario_kind,
                "scenario_id": result.scenario_id,
                "categories": result.badcases,
                "summary": result.report_summary,
            }
            for result in results
            if result.badcases
        ],
        generator_version=GENERATOR_VERSION,
        ontology_version=ONTOLOGY_VERSION,
    )
    json_bytes = (
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    return EvaluationExecution(
        report=report,
        json_bytes=json_bytes,
        markdown_bytes=render_markdown(report),
    )


__all__ = [
    "DEFAULT_SCENARIO_ROOT",
    "EvaluationExecution",
    "render_markdown",
    "resolve_runtime_path",
    "run_evaluation",
]
