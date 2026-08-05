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
) -> ScenarioResult:
    """Score one scenario's diagnosis report against its Ground Truth.

    ``report=None`` means the diagnosis run failed before producing a report;
    the result then only counts toward run_success_rate and carries a
    RUN_FAILURE badcase.
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
    # Evidence validity: fraction of cited evidence codes that the validator
    # did NOT flag as bad references / unsupported. Unsupported claim rate:
    # fraction of root causes flagged R3_NO_EVIDENCE or R10_HIGH_CONF_NO_EV.
    total_causes = len(report.root_causes)
    unsupported_causes = sum(
        1 for i in validation_issues if i.code in {"R3_NO_EVIDENCE", "R10_HIGH_CONF_NO_EV"}
    )
    base.unsupported_claim_rate = (
        ((unsupported_causes / total_causes) if total_causes else 0.0)
        if not is_needs_data
        else None
    )

    total_cited = sum(len(rc.evidence_codes) for rc in report.root_causes)
    bad_refs = sum(1 for i in validation_issues if i.code == "R2_BAD_EVIDENCE_REF")
    base.evidence_validity_rate = (
        (max(0.0, (total_cited - bad_refs) / total_cited) if total_cited else 1.0)
        if not is_needs_data
        else None
    )

    # --- Loss attribution ----------------------------------------------------
    # GT does not carry an expected lost-intent figure, so we measure internal
    # consistency: |estimated - (explained + unexplained)|. A well-formed report
    # has estimated == explained + unexplained, so error → 0.
    if not is_needs_data:
        estimated = report.total_estimated_lost_intents
        accounted = report.explained_lost_intents + report.unexplained_lost_intents
        base.loss_attribution_abs_error = abs(estimated - accounted)

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
    if base.loss_attribution_abs_error and base.loss_attribution_abs_error > 0:
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
        r.loss_attribution_abs_error for r in scored if r.loss_attribution_abs_error is not None
    ]
    tool_calls = [r.tool_call_count for r in scored if r.tool_call_count is not None]
    latencies = [r.latency_ms for r in results if r.latency_ms is not None]

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
        loss_attribution_mae=_mean([float(e) for e in loss_errs]) if loss_errs else None,
        tool_call_count_mean=_mean([float(t) for t in tool_calls]) if tool_calls else None,
        latency_ms_mean=_mean([float(lat) for lat in latencies]) if latencies else None,
        badcase_count=badcase_count,
    )
