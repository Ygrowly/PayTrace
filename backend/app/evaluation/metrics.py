"""Metric computation for evaluation (plan § 20.2).

Pure functions: take a ``DiagnosisReport`` + ``GroundTruth`` (+ validation
issues) and produce a ``ScenarioResult``. No I/O, no DB — fully deterministic
and unit-testable.

Ground Truth isolation (§ 20.1): this module may import Ground Truth models
because it is part of the evaluation path, which runs *after* diagnosis.
"""

from collections.abc import Sequence

from app.diagnosis.report import DiagnosisReport
from app.diagnosis.validator import ValidationIssue
from app.evaluation.models import AggregateMetrics, BadcaseCategory, ScenarioResult
from app.harness.scenarios.ground_truth import GroundTruth
from app.tools.base import Evidence, ToolResult

# Relative loss-attribution error above which a scenario is flagged as a
# material misestimate rather than routine estimation drift.
_LOSS_ERROR_BADGE_THRESHOLD = 0.25


def _jaccard(predicted: set[str], expected: set[str]) -> float:
    if not predicted and not expected:
        return 1.0
    union = predicted | expected
    if not union:
        return 1.0
    return len(predicted & expected) / len(union)


def _prf(predicted: set[str], expected: set[str]) -> tuple[float, float, float]:
    """Precision / recall / F1 for a set comparison. Empty-vs-empty = perfect."""
    if not predicted and not expected:
        return 1.0, 1.0, 1.0
    if not predicted:
        return 0.0, 0.0, 0.0
    if not expected:
        return 0.0, 0.0, 0.0
    tp = len(predicted & expected)
    precision = tp / len(predicted)
    recall = tp / len(expected)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def score_scenario(
    *,
    scenario_kind: str,
    report: DiagnosisReport | None,
    ground_truth: GroundTruth,
    validation_issues: Sequence[ValidationIssue] = (),
    diagnosis_status: str = "SUCCEEDED",
    latency_ms: int | None = None,
    run_evidence: Sequence[Evidence] = (),
    tool_results: Sequence[ToolResult] = (),
) -> ScenarioResult:
    """Score one scenario's diagnosis report against its Ground Truth.

    ``report=None`` means the diagnosis run failed before producing a report;
    the result then only counts toward run_success_rate and carries a
    RUN_FAILURE badcase.

    ``run_evidence`` is the run's evidence ledger and ``tool_results`` its tool
    trace; together they check that a cited code exists *and* came from a tool
    call that actually succeeded.
    """
    expected_stages = set(ground_truth.expected_anomalous_stages)
    expected_causes = set(ground_truth.expected_root_causes)
    expected_gaps = set(ground_truth.expected_data_gaps)

    base = ScenarioResult(
        scenario_kind=scenario_kind,
        scenario_id=ground_truth.scenario_id,
        diagnosis_status=diagnosis_status,
        expected_anomalous_stages=sorted(expected_stages),
        expected_root_causes=sorted(expected_causes),
        expected_data_gaps=sorted(expected_gaps),
        latency_ms=latency_ms,
    )

    if report is None:
        base.badcases = ["RUN_FAILURE"]
        return base

    predicted_stages = set(report.anomalous_stages)
    predicted_causes = {rc.label for rc in report.root_causes}
    predicted_gaps = set(report.missing_data)

    base.predicted_anomalous_stages = sorted(predicted_stages)
    base.predicted_root_causes = sorted(predicted_causes)
    base.predicted_missing_data = sorted(predicted_gaps)
    base.adapter_name = report.adapter_name
    base.model_name = report.model_name
    base.fallback_used = report.fallback_used
    base.fallback_reason = report.fallback_reason
    base.input_tokens = report.input_tokens
    base.output_tokens = report.output_tokens
    base.validation_issue_codes = sorted({i.code for i in validation_issues})

    # A NEEDS_DATA report is a valid safety outcome for a data-gap scenario;
    # it must not be scored as a root-cause miss before the missing data is
    # available. The dedicated DATA_GAP_MISS check below still catches an
    # unsafe or incomplete data-quality response.
    is_needs_data = diagnosis_status == "NEEDS_DATA"

    # --- Stage localization ------------------------------------------------
    if not is_needs_data:
        base.stage_exact = predicted_stages == expected_stages
        base.stage_overlap = _jaccard(predicted_stages, expected_stages)

    # --- Root cause set P/R/F1 ---------------------------------------------
    if not is_needs_data:
        precision, recall, f1 = _prf(predicted_causes, expected_causes)
        base.root_cause_precision = precision
        base.root_cause_recall = recall
        base.root_cause_f1 = f1

    # --- Evidence validity & unsupported claims -----------------------------
    # Evidence validity: fraction of cited codes that are both registered in
    # this run AND produced by a tool call that actually succeeded. A code from
    # a partial/failed call is a citation the system cannot stand behind.
    # Unsupported claim rate: fraction of claims published as UNKNOWN, i.e.
    # claims the evidence contract could not carry. Counted per claim — the
    # former issue-counting version double-counted a single claim that tripped
    # more than one rule.
    total_causes = len(report.root_causes)
    unsupported_causes = sum(1 for rc in report.root_causes if rc.support_status == "UNKNOWN")
    base.unsupported_claim_rate = (
        ((unsupported_causes / total_causes) if total_causes else 0.0)
        if not is_needs_data
        else None
    )

    successful_calls = {r.tool_call_id for r in tool_results if r.status == "success"}
    cited = [code for rc in report.root_causes for code in rc.evidence_codes]
    total_cited = len(cited)
    if total_cited and run_evidence and successful_calls:
        by_code = {e.evidence_code: e for e in run_evidence}
        citable = sum(
            1
            for code in cited
            if code in by_code and by_code[code].tool_call_id in successful_calls
        )
    else:
        # No ledger/trace to check against (direct caller): fall back to
        # counting citations. The evaluation runner always passes both.
        citable = total_cited
    base.evidence_validity_rate = (
        (citable / total_cited if total_cited else 1.0) if not is_needs_data else None
    )

    # --- Loss attribution ----------------------------------------------------
    # Absolute relative error against the injected fault's true impact. The
    # previous version compared the report against itself
    # (|total - (explained + unexplained)|), which a well-formed report always
    # satisfies — it measured formatting, not accuracy.
    if not is_needs_data:
        expected_lost = ground_truth.expected_lost_intents
        base.loss_attribution_rel_error = abs(
            report.total_estimated_lost_intents - expected_lost
        ) / max(expected_lost, 1)

    # --- Tool call count (from distinct tool_call_ids cited in evidence) -----
    # The report does not carry the ledger; approximate via evidence codes,
    # which are 1:1 with tool-produced Evidence records.
    base.tool_call_count = None  # populated by the runner when ledger is available

    # --- Badcase classification ----------------------------------------------
    badcases: list[BadcaseCategory] = []
    if not is_needs_data and expected_stages - predicted_stages:
        badcases.append("STAGE_MISS")
    if not is_needs_data and predicted_stages - expected_stages:
        badcases.append("STAGE_FALSE_POSITIVE")
    if not is_needs_data and expected_causes - predicted_causes:
        badcases.append("ROOT_CAUSE_MISS")
    if not is_needs_data and predicted_causes - expected_causes:
        badcases.append("ROOT_CAUSE_FALSE_POSITIVE")
    if not is_needs_data and unsupported_causes:
        badcases.append("UNSUPPORTED_CLAIM")
    rel_error = base.loss_attribution_rel_error
    if rel_error is not None and rel_error > _LOSS_ERROR_BADGE_THRESHOLD:
        badcases.append("LOSS_ATTRIBUTION_ERROR")

    def _gap_is_reported(expected_gap: str) -> bool:
        return any(expected_gap == item or expected_gap in item for item in predicted_gaps)

    if expected_gaps and not all(_gap_is_reported(gap) for gap in expected_gaps):
        badcases.append("DATA_GAP_MISS")
    base.badcases = badcases

    return base


def aggregate(results: Sequence[ScenarioResult]) -> AggregateMetrics:
    """Aggregate per-scenario results into summary metrics (§ 20.2)."""
    n = len(results)
    if n == 0:
        return AggregateMetrics(
            scenario_count=0,
            succeeded_count=0,
            run_success_rate=0.0,
            stage_localization_exact_rate=0.0,
            stage_localization_overlap_mean=0.0,
            root_cause_precision_mean=0.0,
            root_cause_recall_mean=0.0,
            root_cause_f1_mean=0.0,
            evidence_validity_rate_mean=0.0,
            unsupported_claim_rate_mean=0.0,
            badcase_count=0,
        )

    def _mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    succeeded = [r for r in results if r.diagnosis_status in ("SUCCEEDED", "NEEDS_DATA")]
    scored = [r for r in results if r.root_cause_f1 is not None]

    stage_exact = [r for r in scored if r.stage_exact]
    overlaps = [r.stage_overlap for r in scored if r.stage_overlap is not None]
    precisions = [r.root_cause_precision for r in scored if r.root_cause_precision is not None]
    recalls = [r.root_cause_recall for r in scored if r.root_cause_recall is not None]
    f1s = [r.root_cause_f1 for r in scored if r.root_cause_f1 is not None]
    ev_rates = [r.evidence_validity_rate for r in scored if r.evidence_validity_rate is not None]
    uc_rates = [r.unsupported_claim_rate for r in scored if r.unsupported_claim_rate is not None]
    loss_errs = [
        r.loss_attribution_rel_error for r in scored if r.loss_attribution_rel_error is not None
    ]
    tool_calls = [r.tool_call_count for r in scored if r.tool_call_count is not None]
    latencies = [r.latency_ms for r in results if r.latency_ms is not None]
    input_tokens = [r.input_tokens for r in results if r.input_tokens is not None]
    output_tokens = [r.output_tokens for r in results if r.output_tokens is not None]
    # A run counts as a model invocation only when a model was actually
    # reached: B1 through the report adapter, B2 through the investigation
    # policy. Fallbacks are counted separately and never as invocations.
    model_invocation_count = sum(
        1
        for r in results
        if not r.fallback_used
        and (
            r.adapter_name == "OpenAICompatibleModelAdapter"
            or r.policy_name == "OpenAIToolCallingPolicy"
        )
    )
    fallback_count = sum(1 for r in results if r.fallback_used)

    badcase_count = sum(1 for r in results if r.badcases)

    return AggregateMetrics(
        scenario_count=n,
        succeeded_count=len(succeeded),
        run_success_rate=len(succeeded) / n,
        stage_localization_exact_rate=len(stage_exact) / len(scored) if scored else 0.0,
        stage_localization_overlap_mean=_mean([float(o) for o in overlaps]),
        root_cause_precision_mean=_mean([float(p) for p in precisions]),
        root_cause_recall_mean=_mean([float(r) for r in recalls]),
        root_cause_f1_mean=_mean([float(f) for f in f1s]),
        evidence_validity_rate_mean=_mean([float(e) for e in ev_rates]),
        unsupported_claim_rate_mean=_mean([float(u) for u in uc_rates]),
        loss_attribution_mape=_mean([float(e) for e in loss_errs]) if loss_errs else None,
        tool_call_count_mean=_mean([float(t) for t in tool_calls]) if tool_calls else None,
        latency_ms_mean=_mean([float(lat) for lat in latencies]) if latencies else None,
        badcase_count=badcase_count,
        model_invocation_count=model_invocation_count,
        fallback_count=fallback_count,
        total_input_tokens=sum(input_tokens) if input_tokens else None,
        total_output_tokens=sum(output_tokens) if output_tokens else None,
    )
