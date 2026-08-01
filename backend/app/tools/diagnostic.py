"""The four deterministic diagnosis tools (plan § 13).

Each tool is read-only, calls the PaymentAnalyticsSource protocol, converts
results into EvidenceDrafts, and offloads large result payloads to the
ArtifactStore. No SQL or metric computation happens outside the analytics
source; these tools only orchestrate and summarise.
"""

import json
from typing import Any

from app.analytics.base import (
    BenefitQuery,
    BreakdownQuery,
    FunnelQuery,
    PaymentAnalyticsSource,
    PaymentEventQuery,
)
from app.harness.artifact_store import ArtifactStore
from app.ontology.registry import EvidenceType
from app.tools.base import EvidenceDraft, ToolResult

# Step-rate delta above which a stage is reported as degraded in evidence.
_DEGRADATION_THRESHOLD = 0.05
# Benefit mean-gap shift (minor units) above which friction evidence is raised.
_GAP_SHIFT_THRESHOLD = 100


class _BaseTool:
    name: str
    version: str = "1.0.0"
    read_only: bool = True

    def __init__(
        self, source: PaymentAnalyticsSource, artifacts: ArtifactStore | None = None
    ) -> None:
        self._source = source
        self._artifacts = artifacts

    def _store_artifact(self, tool_call_id: str, kind: str, payload: Any) -> Any:
        if self._artifacts is None:
            return None
        data = json.dumps(payload, indent=2, default=str).encode()
        return self._artifacts.put_bytes(
            f"tool_results/{tool_call_id}/{kind}.json", data, "application/json"
        )


class GetPaymentFunnelTool(_BaseTool):
    name = "get_payment_funnel"

    def run(
        self, tool_call_id: str, *, dataset_ref: str, filters: dict[str, str] | None = None
    ) -> ToolResult:
        res = self._source.get_funnel(FunnelQuery(dataset_ref=dataset_ref, filters=filters or {}))
        artifact = self._store_artifact(tool_call_id, "funnel", res.model_dump())

        evidence: list[EvidenceDraft] = []
        warnings: list[str] = []
        for stage in res.anomalous_stages:
            delta = next(d for d in res.deltas if d.stage == stage)
            evidence.append(
                EvidenceDraft(
                    evidence_type=EvidenceType.FUNNEL_STAGE_DEGRADATION,
                    summary=(
                        f"Stage {stage} degraded: overall rate "
                        f"{delta.baseline_overall_rate:.3f} -> {delta.incident_overall_rate:.3f} "
                        f"(delta {delta.rate_delta:+.3f}), "
                        f"est. lost intents {delta.estimated_lost_intents}"
                    ),
                    metrics={
                        "stage": stage,
                        "baseline_overall_rate": round(delta.baseline_overall_rate, 6),
                        "incident_overall_rate": round(delta.incident_overall_rate, 6),
                        "rate_delta": round(delta.rate_delta, 6),
                        "estimated_lost_intents": delta.estimated_lost_intents,
                    },
                )
            )
        if not res.anomalous_stages:
            warnings.append("no anomalous funnel stages detected")

        summary = (
            f"Funnel: {res.baseline.order_confirmed_count} baseline / "
            f"{res.incident.order_confirmed_count} incident order-confirmed intents; "
            f"anomalous stages: {', '.join(res.anomalous_stages) or 'none'}"
        )
        return ToolResult(
            tool_call_id=tool_call_id,
            tool_name=self.name,
            status="success",
            summary=summary,
            evidence=evidence,
            artifact_ref=artifact,
            row_count=len(res.deltas),
            warnings=warnings,
        )


class BreakdownConversionLossTool(_BaseTool):
    name = "breakdown_conversion_loss"

    def run(
        self,
        tool_call_id: str,
        *,
        dataset_ref: str,
        dimension: str,
        top_k: int = 10,
    ) -> ToolResult:
        res = self._source.breakdown_loss(
            BreakdownQuery(dataset_ref=dataset_ref, dimension=dimension, top_k=top_k)
        )
        artifact = self._store_artifact(tool_call_id, f"breakdown_{dimension}", res.model_dump())

        evidence: list[EvidenceDraft] = []
        for row in res.rows:
            if row.rate_delta < -_DEGRADATION_THRESHOLD and row.estimated_lost_intents > 0:
                evidence.append(
                    EvidenceDraft(
                        evidence_type=EvidenceType.DIMENSION_CONTRIBUTION,
                        summary=(
                            f"{dimension}={row.dimension_value} conversion "
                            f"{row.baseline_rate:.3f} -> {row.incident_rate:.3f} "
                            f"(delta {row.rate_delta:+.3f}), est. lost {row.estimated_lost_intents}"
                        ),
                        metrics={
                            "dimension": dimension,
                            "dimension_value": row.dimension_value,
                            "baseline_rate": round(row.baseline_rate, 6),
                            "incident_rate": round(row.incident_rate, 6),
                            "rate_delta": round(row.rate_delta, 6),
                            "estimated_lost_intents": row.estimated_lost_intents,
                        },
                        dimensions={dimension: row.dimension_value},
                    )
                )
        top = res.rows[0] if res.rows else None
        summary = (
            f"Breakdown by {dimension}: top contributor "
            f"{top.dimension_value if top else 'n/a'} "
            f"(est. lost {top.estimated_lost_intents if top else 0}); "
            f"{len(evidence)} contributing values"
        )
        return ToolResult(
            tool_call_id=tool_call_id,
            tool_name=self.name,
            status="success",
            summary=summary,
            evidence=evidence,
            artifact_ref=artifact,
            row_count=len(res.rows),
        )


class AnalyzeBenefitGapTool(_BaseTool):
    name = "analyze_benefit_gap"

    def run(self, tool_call_id: str, *, dataset_ref: str) -> ToolResult:
        res = self._source.analyze_benefit_gap(BenefitQuery(dataset_ref=dataset_ref))
        artifact = self._store_artifact(tool_call_id, "benefit_gap", res.model_dump())

        evidence: list[EvidenceDraft] = []
        warnings: list[str] = []
        if res.mean_gap_shift_minor > _GAP_SHIFT_THRESHOLD:
            high = next((b for b in res.incident.buckets if b.bucket == ">=1000"), None)
            cancel_rate_str = f"{high.cancel_rate:.3f}" if high else "n/a"
            evidence.append(
                EvidenceDraft(
                    evidence_type=EvidenceType.BENEFIT_GAP_FRICTION,
                    summary=(
                        f"Benefit gap shifted +{res.mean_gap_shift_minor:.0f} minor units "
                        f"(baseline {res.baseline.mean_gap_minor:.0f} -> incident "
                        f"{res.incident.mean_gap_minor:.0f}); high-gap cancel rate "
                        f"{cancel_rate_str}"
                    ),
                    metrics={
                        "mean_gap_shift_minor": round(res.mean_gap_shift_minor, 3),
                        "baseline_mean_gap_minor": round(res.baseline.mean_gap_minor, 3),
                        "incident_mean_gap_minor": round(res.incident.mean_gap_minor, 3),
                        "high_gap_cancel_rate": round(high.cancel_rate, 6) if high else 0.0,
                        "high_gap_reorder_rate": round(high.reorder_rate, 6) if high else 0.0,
                        "high_gap_switch_rate": round(high.switch_method_rate, 6) if high else 0.0,
                    },
                )
            )
        # Plan § 13.3: benefit gap is friction evidence, never sole causal proof.
        warnings.append("benefit gap is observational friction evidence, not sole causal proof")

        summary = (
            f"Benefit gap: mean shift {res.mean_gap_shift_minor:+.0f} minor units; "
            f"{'friction evidence raised' if evidence else 'no significant shift'}"
        )
        return ToolResult(
            tool_call_id=tool_call_id,
            tool_name=self.name,
            status="success",
            summary=summary,
            evidence=evidence,
            artifact_ref=artifact,
            row_count=len(res.incident.buckets),
            warnings=warnings,
        )


class InspectPaymentEventsTool(_BaseTool):
    name = "inspect_payment_events"

    def run(self, tool_call_id: str, *, dataset_ref: str, top_k: int = 10) -> ToolResult:
        res = self._source.inspect_payment_events(
            PaymentEventQuery(dataset_ref=dataset_ref, top_k=top_k)
        )
        artifact = self._store_artifact(tool_call_id, "payment_events", res.model_dump())

        evidence: list[EvidenceDraft] = []
        inc = res.incident
        timeout_count = inc.status_counts.get("TIMEOUT", 0)
        timeout_codes = [e for e in inc.top_error_codes if "TIMEOUT" in e.error_code.upper()]
        if timeout_count > 0 and timeout_codes:
            top_code = timeout_codes[0]
            p95_str = f"{inc.latency.p95_ms:.0f}" if inc.latency.p95_ms is not None else "n/a"
            evidence.append(
                EvidenceDraft(
                    evidence_type=EvidenceType.CHANNEL_TIMEOUT,
                    summary=(
                        f"{timeout_count} payment timeouts; top error {top_code.error_code} "
                        f"({top_code.count}); affected channels: "
                        f"{', '.join(inc.affected_payment_channels) or 'n/a'}; "
                        f"p95 latency {p95_str} ms"
                    ),
                    metrics={
                        "timeout_count": timeout_count,
                        "top_error_code": top_code.error_code,
                        "top_error_count": top_code.count,
                        "p95_latency_ms": round(inc.latency.p95_ms or 0.0, 1),
                        "p99_latency_ms": round(inc.latency.p99_ms or 0.0, 1),
                    },
                    dimensions={
                        "payment_channel": ",".join(inc.affected_payment_channels),
                    },
                )
            )
        # Error-code concentration evidence (non-timeout).
        other_codes = [e for e in inc.top_error_codes if "TIMEOUT" not in e.error_code.upper()]
        if other_codes:
            top = other_codes[0]
            evidence.append(
                EvidenceDraft(
                    evidence_type=EvidenceType.ERROR_CODE_CONCENTRATION,
                    summary=(
                        f"Top non-timeout error code {top.error_code} " f"({top.count} occurrences)"
                    ),
                    metrics={"error_code": top.error_code, "count": top.count},
                )
            )

        summary = (
            f"Payment events: incident statuses {inc.status_counts}; "
            f"timeouts={timeout_count}; affected channels "
            f"{', '.join(inc.affected_payment_channels) or 'none'}"
        )
        return ToolResult(
            tool_call_id=tool_call_id,
            tool_name=self.name,
            status="success",
            summary=summary,
            evidence=evidence,
            artifact_ref=artifact,
            row_count=sum(inc.status_counts.values()),
        )


def build_default_tools(
    source: PaymentAnalyticsSource, artifacts: ArtifactStore | None = None
) -> list:
    return [
        GetPaymentFunnelTool(source, artifacts),
        BreakdownConversionLossTool(source, artifacts),
        AnalyzeBenefitGapTool(source, artifacts),
        InspectPaymentEventsTool(source, artifacts),
    ]
