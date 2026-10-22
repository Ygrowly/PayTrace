"""Evaluation domain models (plan § 20).

These models describe the *scored output* of an EvaluationRun: per-scenario
comparison between the diagnosis prediction and Ground Truth, aggregate
metrics, and badcase classification.

Ground Truth isolation (§ 20.1): this module is the ONLY place (besides the
scenario harness itself) that may import ``GroundTruthLoader``. The diagnosis
path never touches Ground Truth.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

# Badcase categories (§ 20.4 badcase 分类). A scenario result may carry
# several; empty list = clean pass.
BadcaseCategory = Literal[
    "STAGE_MISS",  # expected anomalous stage not detected
    "STAGE_FALSE_POSITIVE",  # predicted stage not in GT
    "ROOT_CAUSE_MISS",  # expected root cause absent from prediction
    "ROOT_CAUSE_FALSE_POSITIVE",  # predicted root cause not in GT
    "UNSUPPORTED_CLAIM",  # a claim the evidence contract could not carry
    "LOSS_ATTRIBUTION_ERROR",  # relative loss error beyond tolerance
    "RUN_FAILURE",  # diagnosis run did not succeed
    "DATA_GAP_MISS",  # expected data gap not surfaced in missing_data
]


class ScenarioResult(BaseModel):
    """Per-scenario evaluation outcome (prediction vs Ground Truth)."""

    scenario_kind: str
    scenario_id: str
    diagnosis_status: str  # SUCCEEDED / NEEDS_DATA / FAILED
    predicted_anomalous_stages: list[str] = Field(default_factory=list)
    expected_anomalous_stages: list[str] = Field(default_factory=list)
    predicted_root_causes: list[str] = Field(default_factory=list)
    expected_root_causes: list[str] = Field(default_factory=list)
    predicted_missing_data: list[str] = Field(default_factory=list)
    expected_data_gaps: list[str] = Field(default_factory=list)
    # Per-scenario metric values (None when the run failed before producing
    # a report — counted in run_success_rate only).
    stage_exact: bool | None = None
    stage_overlap: float | None = None  # Jaccard |P∩E| / |P∪E|
    root_cause_precision: float | None = None
    root_cause_recall: float | None = None
    root_cause_f1: float | None = None
    evidence_validity_rate: float | None = None  # citable evidence / total cited
    unsupported_claim_rate: float | None = None  # UNKNOWN claims / total claims
    # |estimated lost - GT fault-attributable lost| / max(GT lost, 1)
    loss_attribution_rel_error: float | None = None
    tool_call_count: int | None = None
    latency_ms: int | None = None
    report_summary: str | None = None
    unexplained_lost_intents: int | None = None
    recommended_actions: list[str] = Field(default_factory=list)
    adapter_name: str | None = None
    model_name: str | None = None
    # Which evidence-gathering mode ran (B0 fixed pipeline / B2 investigation)
    # and, for B2, which policy drove it. The report's own adapter provenance
    # above refers to the writer, not the investigator.
    agent_mode: str = "B0"
    policy_name: str | None = None
    # True when any model step in this scenario fell back to a deterministic
    # path. A fallback run must never be reported as a successful model run.
    fallback_used: bool = False
    fallback_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    tool_trace: list[dict[str, Any]] = Field(default_factory=list)
    # Validator codes raised on the published report, so a badcase can be
    # traced back to the rule that fired rather than only to its symptom.
    validation_issue_codes: list[str] = Field(default_factory=list)
    badcases: list[BadcaseCategory] = Field(default_factory=list)


class AggregateMetrics(BaseModel):
    """Summary metrics across all scenarios in one EvaluationRun (§ 20.2)."""

    scenario_count: int
    succeeded_count: int
    run_success_rate: float
    stage_localization_exact_rate: float
    stage_localization_overlap_mean: float
    root_cause_precision_mean: float
    root_cause_recall_mean: float
    root_cause_f1_mean: float
    evidence_validity_rate_mean: float
    unsupported_claim_rate_mean: float
    # Mean of |relative error| against Ground Truth fault impact, i.e. MAPE.
    # None only when no scenario produced a scored report.
    loss_attribution_mape: float | None = None
    tool_call_count_mean: float | None = None
    latency_ms_mean: float | None = None
    badcase_count: int
    model_invocation_count: int = 0
    fallback_count: int = 0
    # Token usage / estimated cost — nullable per § 20.2 (B0 rule-based = none).
    total_input_tokens: int | None = None
    total_output_tokens: int | None = None
    estimated_cost: float | None = None


class EvaluationReport(BaseModel):
    model_config = {"protected_namespaces": ()}
    """Full evaluation report — serialised to JSON + Markdown artifacts."""

    evaluation_run_id: str
    model_mode: str
    prompt_version: str | None = None
    seed: int
    num_intents: int
    metrics: AggregateMetrics
    scenario_results: list[ScenarioResult]
    badcases: list[dict[str, Any]] = Field(default_factory=list)
    generator_version: str
    ontology_version: str
