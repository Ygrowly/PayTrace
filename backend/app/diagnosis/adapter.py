"""RuleBasedModelAdapter — deterministic rules, no API key (plan § 15.1).

Uses ONLY the evidence in DiagnosisContext. Does not read Ground Truth or
scenario filenames. Serves as the M2 baseline adapter and the fallback when
a real model is unavailable or validator retries are exhausted.
"""

from app.diagnosis.model import DiagnosisContext
from app.diagnosis.report import DiagnosisReport, RootCause
from app.ontology.registry import EvidenceType


class RuleBasedModelAdapter:
    """Deterministic diagnosis from evidence summaries.

    Rules (ordered, first match wins):
    1. Missing data → NEEDS_DATA
    2. CHANNEL_TIMEOUT + BENEFIT_GAP_FRICTION → dual root cause
    3. CHANNEL_TIMEOUT only          → CHANNEL_TIMEOUT
    4. BENEFIT_GAP_FRICTION only     → BENEFIT_SELECTION_FRICTION
    5. Anomalous stages + evidence   → UNKNOWN
    6. No significant evidence       → NORMAL_PAYMENT_FAILURE (LOW confidence)
    """

    def __init__(self, validator_version: str = "paytrace.validator.v1") -> None:
        self._validator_version = validator_version

    def generate(self, ctx: DiagnosisContext) -> DiagnosisReport:
        evidence_types = {e.evidence_type for e in ctx.evidence_list}

        # Estimate total lost intents from funnel stage degradation evidence.
        total_lost = 0
        for ev in ctx.evidence_list:
            if ev.evidence_type == EvidenceType.FUNNEL_STAGE_DEGRADATION:
                total_lost += ev.metrics.get("estimated_lost_intents", 0)

        # Rule 1: data gaps → NEEDS_DATA
        if ctx.missing_data:
            return DiagnosisReport(
                incident_id=ctx.incident_id,
                diagnosis_run_id=ctx.diagnosis_run_id,
                status="NEEDS_DATA",
                summary=(
                    f"Diagnosis blocked: {len(ctx.missing_data)} data quality issues detected. "
                    f"Missing: {', '.join(ctx.missing_data[:5])}"
                ),
                anomalous_stages=ctx.anomalous_stages,
                root_causes=[],
                total_estimated_lost_intents=total_lost,
                explained_lost_intents=0,
                unexplained_lost_intents=total_lost,
                missing_data=ctx.missing_data,
                recommended_actions=["Request complete data from the affected periods."],
                ontology_version=ctx.ontology_version,
                validator_version=self._validator_version,
            )

        has_timeout_ev = EvidenceType.CHANNEL_TIMEOUT in evidence_types
        has_benefit_ev = EvidenceType.BENEFIT_GAP_FRICTION in evidence_types
        has_stage_degradation = EvidenceType.FUNNEL_STAGE_DEGRADATION in evidence_types
        has_dimension_ev = EvidenceType.DIMENSION_CONTRIBUTION in evidence_types

        root_causes: list[RootCause] = []
        explained = 0

        # Estimate lost intents per evidence type from matching stage/dimension evidence.
        timeout_lost = _estimate_lost_for_evidence(
            ctx, (EvidenceType.CHANNEL_TIMEOUT, EvidenceType.DIMENSION_CONTRIBUTION)
        )
        benefit_lost = _estimate_lost_for_evidence(ctx, (EvidenceType.BENEFIT_GAP_FRICTION,))

        # Rule 2–4: build root causes from evidence
        timeout_codes = _evidence_codes_for(ctx, EvidenceType.CHANNEL_TIMEOUT)
        benefit_codes = _evidence_codes_for(ctx, EvidenceType.BENEFIT_GAP_FRICTION)
        stage_codes = _evidence_codes_for(ctx, EvidenceType.FUNNEL_STAGE_DEGRADATION)
        dim_codes = _evidence_codes_for(ctx, EvidenceType.DIMENSION_CONTRIBUTION)
        error_codes = _evidence_codes_for(ctx, EvidenceType.ERROR_CODE_CONCENTRATION)

        rank = 1

        if has_timeout_ev:
            rc_lost = min(timeout_lost, total_lost) if total_lost > 0 else timeout_lost
            root_causes.append(
                RootCause(
                    label="CHANNEL_TIMEOUT",
                    category="infrastructure",
                    confidence="HIGH",
                    estimated_lost_intents=rc_lost,
                    explanation=(
                        f"Channel timeout evidence with {timeout_lost} estimated lost intents "
                        f"in payment channel timeouts."
                    ),
                    evidence_codes=timeout_codes + dim_codes,
                    rank=rank,
                )
            )
            explained += rc_lost
            rank += 1

        if has_benefit_ev:
            rc_lost = min(benefit_lost, total_lost) if total_lost > 0 else benefit_lost
            root_causes.append(
                RootCause(
                    label="BENEFIT_SELECTION_FRICTION",
                    category="product",
                    confidence="MEDIUM",
                    estimated_lost_intents=rc_lost,
                    explanation=(
                        f"Benefit gap friction evidence indicates a pricing or discount "
                        f"selection issue with {benefit_lost} estimated lost intents. "
                        f"(Observational friction evidence, not sole causal proof.)"
                    ),
                    evidence_codes=benefit_codes + stage_codes,
                    rank=rank,
                )
            )
            explained += rc_lost
            rank += 1

        if not root_causes and (has_stage_degradation or has_dimension_ev):
            # Rule 5: evidence exists but doesn't match known patterns
            all_codes = stage_codes + dim_codes + error_codes
            root_causes.append(
                RootCause(
                    label="UNKNOWN",
                    category=None,
                    confidence="LOW",
                    estimated_lost_intents=total_lost,
                    explanation=(
                        f"Funnel stage degradation detected "
                        f"({', '.join(ctx.anomalous_stages) or 'none'}) "
                        f"but no specific fault pattern matched."
                    ),
                    evidence_codes=all_codes,
                    rank=1,
                )
            )
            explained = total_lost

        if not root_causes:
            # Rule 6: no significant evidence — normal
            root_causes.append(
                RootCause(
                    label="NORMAL_PAYMENT_FAILURE",
                    category=None,
                    confidence="LOW",
                    estimated_lost_intents=0,
                    explanation="No significant evidence of a payment anomaly detected.",
                    evidence_codes=[],
                    rank=1,
                )
            )

        # Evidence-level loss estimates can overlap across tools (each tool
        # estimates loss from its own perspective), so cap explained at total.
        explained = min(explained, total_lost)
        unexplained = max(0, total_lost - explained)
        action_items = _recommend_actions(evidence_types, ctx.anomalous_stages)

        return DiagnosisReport(
            incident_id=ctx.incident_id,
            diagnosis_run_id=ctx.diagnosis_run_id,
            status="SUCCEEDED",
            summary=_build_summary(root_causes, total_lost, unexplained),
            anomalous_stages=ctx.anomalous_stages,
            root_causes=root_causes,
            total_estimated_lost_intents=total_lost,
            explained_lost_intents=explained,
            unexplained_lost_intents=unexplained,
            missing_data=[],
            recommended_actions=action_items,
            ontology_version=ctx.ontology_version,
            validator_version=self._validator_version,
        )


def _evidence_codes_for(ctx: DiagnosisContext, ev_type: EvidenceType) -> list[str]:
    return [e.evidence_code for e in ctx.evidence_list if e.evidence_type == ev_type]


def _estimate_lost_for_evidence(ctx: DiagnosisContext, ev_types: tuple[EvidenceType, ...]) -> int:
    """Sum estimated_lost_intents from matching evidence types and related dimension evidence."""
    total = 0
    for ev in ctx.evidence_list:
        if ev.evidence_type in ev_types:
            total += ev.metrics.get("estimated_lost_intents", 0)
    return total


def _build_summary(root_causes: list[RootCause], total: int, unexplained: int) -> str:
    if not root_causes:
        return "No root causes identified."
    parts: list[str] = []
    for rc in root_causes:
        label = rc.label
        conf = rc.confidence
        lost = rc.estimated_lost_intents or 0
        parts.append(f"{label} [{conf}] ({lost} est. lost)")
    base = "; ".join(parts)
    if unexplained > 0:
        base += f"; {unexplained} unexplained lost intents"
    return f"Total estimated lost intents: {total}. Root causes: {base}."


def _recommend_actions(
    evidence_types: set[EvidenceType],
    anomalous_stages: list[str],
) -> list[str]:
    actions: list[str] = []
    if EvidenceType.CHANNEL_TIMEOUT in evidence_types:
        actions.append(
            "Investigate payment channel infrastructure for timeouts and latency spikes."
        )
    if EvidenceType.BENEFIT_GAP_FRICTION in evidence_types:
        actions.append(
            "Review benefit/discount selection UX and pricing logic for friction points."
        )
    if EvidenceType.FUNNEL_STAGE_DEGRADATION in evidence_types:
        actions.append(
            f"Inspect funnel stages: {', '.join(anomalous_stages) or 'anomalous'} for root cause."
        )
    if EvidenceType.ERROR_CODE_CONCENTRATION in evidence_types:
        actions.append("Investigate concentrated error codes for recurring patterns.")
    if not actions:
        actions.append("Monitor payment conversion rates for recurrence.")
        actions.append("Consider increasing observation window for statistical significance.")
    return actions
