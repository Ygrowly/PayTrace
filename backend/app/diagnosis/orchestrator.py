"""DiagnosisOrchestrator — the diagnosis pipeline (plan § 14.1).

Two evidence-gathering modes feed the *same* report step, so they can be
compared with everything downstream held constant:

* ``B0`` — the fixed six-tool workflow.
* ``B2`` — the governed Diagnostic Harness, where a policy decides which tool
  to call next under a routed capability bundle, a budget, and a hypothesis
  ledger.

Either way the flow continues through ContextBuilder → ModelAdapter →
ReportValidator.

No Celery, no DB persistence, no SSE — those are the task/API layers' concerns.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from app.analytics.base import PaymentAnalyticsSource
from app.diagnosis.adapter import RuleBasedModelAdapter
from app.diagnosis.context import ContextBuilder
from app.diagnosis.model import DiagnosisContext, ModelAdapter
from app.diagnosis.report import DiagnosisReport, RootCause
from app.diagnosis.validator import ReportValidator, ValidationIssue, resolve_support_status
from app.harness.artifact_store import ArtifactStore
from app.harness.harness import DEFAULT_MAX_TOOL_CALLS, DiagnosticHarness
from app.harness.investigation import InvestigationPolicy
from app.harness.ledger import Hypothesis
from app.tools.base import EvidenceLedger, ToolPolicy, ToolRegistry, ToolResult
from app.tools.diagnostic import build_default_tools

AgentMode = Literal["B0", "B2"]

_DEFAULT_DIMENSIONS = ("payment_channel", "payment_method")

# Issues that make a report unpublishable. Everything else is either corrected
# by the evidence contract above or returned as an advisory warning.
_BLOCKING_CODES = frozenset({"R12_SCHEMA_VERSION", "R3_NO_EVIDENCE"})


class OrchestratorFailure(Exception):
    """Raised when the orchestrator cannot produce a valid report."""


@dataclass
class DiagnosisExecution:
    """A report plus the trace needed by API and evaluation consumers.

    ``run()`` intentionally keeps returning only ``DiagnosisReport`` for the
    M2 callers. M3 consumers use this richer result so scoring and the UI can
    inspect system-produced evidence and tool timings without re-running the
    diagnostic workflow or putting business calculations in the frontend.

    The harness fields stay empty for B0, where no investigation loop ran.
    """

    report: DiagnosisReport
    ledger: EvidenceLedger
    tool_results: tuple[ToolResult, ...]
    validation_issues: tuple[ValidationIssue, ...]
    agent_mode: AgentMode = "B0"
    hypotheses: tuple[Hypothesis, ...] = ()
    steps: tuple[dict[str, Any], ...] = ()
    blocked_calls: tuple[dict[str, Any], ...] = ()
    degradations: tuple[str, ...] = ()
    early_exit_reason: str | None = None
    incident_scope: dict[str, Any] = field(default_factory=dict)
    capability_bundle: dict[str, Any] = field(default_factory=dict)
    # Which investigation policy ran, and whether it reached a model at all.
    # Kept separate from the report's own adapter provenance: B2's report is
    # written by the rule adapter even when the investigation used a model.
    policy_name: str | None = None
    # The model the policy was configured to use — what was *requested*, which
    # policy_fallback_used tells you whether it was actually reached.
    policy_model_name: str | None = None
    policy_fallback_used: bool = False
    policy_fallback_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class DiagnosisOrchestrator:
    """Runs the diagnosis pipeline in B0 (fixed workflow) or B2 (harness) mode.

    Workflow (plan § 14.1), shared by both modes:

    1. Validate dataset → data quality checks
    2. Gather evidence — fixed tool pipeline (B0) or governed investigation (B2)
    3. Evidence Ledger → Context Builder
    4. Model Adapter → Report Validator → one correction retry
    """

    def __init__(
        self,
        source: PaymentAnalyticsSource,
        artifacts: ArtifactStore | None = None,
        adapter: ModelAdapter | None = None,
        validator: ReportValidator | None = None,
        dimensions: tuple[str, ...] = _DEFAULT_DIMENSIONS,
        max_retries: int = 1,
        evidence_code_prefix: str = "",
        agent_mode: AgentMode = "B0",
        investigation_policy: InvestigationPolicy | None = None,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    ) -> None:
        self._source = source
        self._artifacts = artifacts
        self._adapter = adapter or RuleBasedModelAdapter()
        self._validator = validator or ReportValidator()
        self._dimensions = dimensions
        self._max_retries = max_retries
        self._evidence_code_prefix = evidence_code_prefix
        self._agent_mode: AgentMode = agent_mode
        self._investigation_policy = investigation_policy
        self._max_tool_calls = max_tool_calls

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        dataset_ref: str,
        *,
        incident_id: str | None = None,
        diagnosis_run_id: str | None = None,
        scenario_id: str = "",
    ) -> DiagnosisReport:
        """Execute the full diagnosis pipeline and return a validated report.

        Args:
            dataset_ref: Path to the Parquet dataset file.
            incident_id: Unique incident identifier (auto-generated if None).
            diagnosis_run_id: Unique run identifier (auto-generated if None).
            scenario_id: Optional scenario kind label for traceability.
        """
        return self.run_detailed(
            dataset_ref,
            incident_id=incident_id,
            diagnosis_run_id=diagnosis_run_id,
            scenario_id=scenario_id,
        ).report

    def run_detailed(
        self,
        dataset_ref: str,
        *,
        incident_id: str | None = None,
        diagnosis_run_id: str | None = None,
        scenario_id: str = "",
    ) -> DiagnosisExecution:
        """Run diagnosis and retain evidence, tool results, and validation.

        The evidence-gathering step depends on ``agent_mode``; everything after
        it — context building, report generation, validation — is identical, so
        B0 and B2 differ only in how the evidence was collected.
        """
        iid = incident_id or f"inc-{uuid.uuid4().hex[:12]}"
        rid = diagnosis_run_id or f"run-{uuid.uuid4().hex[:12]}"

        harness_result = None
        if self._agent_mode == "B2":
            harness_result = self._run_harness(
                dataset_ref, incident_id=iid, run_id=rid, scenario_id=scenario_id
            )
            ledger = harness_result.ledger
            anomalous_stages = harness_result.anomalous_stages
            funnel_summary = harness_result.funnel_summary
            tool_results = list(harness_result.tool_results)
            missing_data = harness_result.missing_data
        else:
            # Step 1: validate dataset
            missing_data, _ = self._validate_dataset(dataset_ref)
            # Step 2: execute fixed tool pipeline
            ledger, anomalous_stages, funnel_summary, tool_results = self._run_tool_pipeline(
                dataset_ref
            )

        # Step 3: build context
        context = ContextBuilder().build(
            incident_id=iid,
            diagnosis_run_id=rid,
            scenario_id=scenario_id,
            funnel_summary=funnel_summary,
            anomalous_stages=anomalous_stages,
            ledger=ledger,
            missing_data=missing_data,
        )

        # Step 4: generate + validate with one correction retry
        report, issues = self._generate_with_retry(context)

        # Step 5: apply the evidence contract to the report that will actually
        # be published, then re-validate so `validation_issues` describes the
        # artifact consumers receive rather than the adapter's raw output.
        report, contract_notes = self._apply_evidence_contract(report, context)
        issues = self._validator.validate(report, context) + contract_notes

        # Blocking issues are those that make the report unpublishable: a schema
        # mismatch, or a NEEDS_DATA report that still asserts root causes.
        # Evidence-contract downgrades are applied above, not raised — an
        # UNKNOWN claim is a legitimate published outcome (notes § 9.4).
        blocking = [i for i in issues if not i.retryable and i.code in _BLOCKING_CODES]
        if blocking:
            codes = ", ".join(i.code for i in blocking)
            raise OrchestratorFailure(
                f"report has blocking validation issues after {self._max_retries} "
                f"retries: {codes}"
            )

        return DiagnosisExecution(
            report=report,
            ledger=ledger,
            tool_results=tuple(tool_results),
            validation_issues=tuple(issues),
            agent_mode=self._agent_mode,
            hypotheses=harness_result.hypotheses if harness_result else (),
            steps=tuple(harness_result.steps) if harness_result else (),
            blocked_calls=tuple(harness_result.blocked_calls) if harness_result else (),
            degradations=tuple(harness_result.degradations) if harness_result else (),
            early_exit_reason=harness_result.early_exit_reason if harness_result else None,
            incident_scope=harness_result.incident_scope if harness_result else {},
            capability_bundle=(
                {
                    "signals": list(harness_result.bundle.signals),
                    "allowed_tools": sorted(harness_result.bundle.allowed_tools),
                    "rationale": harness_result.bundle.rationale,
                }
                if harness_result
                else {}
            ),
            policy_name=harness_result.policy_name if harness_result else None,
            policy_model_name=harness_result.policy_model_name if harness_result else None,
            policy_fallback_used=harness_result.fallback_used if harness_result else False,
            policy_fallback_reason=harness_result.fallback_reason if harness_result else None,
            input_tokens=harness_result.input_tokens if harness_result else None,
            output_tokens=harness_result.output_tokens if harness_result else None,
        )

    def _run_harness(self, dataset_ref: str, *, incident_id: str, run_id: str, scenario_id: str):
        """Delegate evidence gathering to the governed investigation loop."""
        harness = DiagnosticHarness(
            self._source,
            artifacts=self._artifacts,
            policy=self._investigation_policy,
            max_tool_calls=self._max_tool_calls,
            evidence_code_prefix=self._evidence_code_prefix,
        )
        return harness.run(
            dataset_ref,
            incident_id=incident_id,
            diagnosis_run_id=run_id,
            scenario_id=scenario_id,
        )

    def _apply_evidence_contract(
        self, report: DiagnosisReport, context: DiagnosisContext
    ) -> tuple[DiagnosisReport, list[ValidationIssue]]:
        """Downgrade claims the evidence cannot carry and rebalance the ledger.

        A claim with no positive evidence is republished as UNKNOWN, and its loss
        estimate moves from ``explained`` to ``unexplained``. The downgrade is
        returned as a ValidationIssue so the trace records what changed — the
        report is never silently altered.
        """
        if not report.root_causes:
            return report, []

        run_evidence = {e.evidence_code: e for e in context.evidence_list}
        notes: list[ValidationIssue] = []
        causes: list[RootCause] = []
        explainable = 0

        for i, rc in enumerate(report.root_causes):
            status, reason = resolve_support_status(rc.label, rc.evidence_codes, run_evidence)
            if status != rc.support_status:
                notes.append(
                    ValidationIssue(
                        "R14_UNSUPPORTED_STATUS",
                        f"root_causes[{i}].support_status",
                        f"{rc.label}: {rc.support_status} -> {status} ({reason})",
                        retryable=False,
                    )
                )
                causes.append(rc.model_copy(update={"support_status": status}))
            else:
                causes.append(rc)
            if status != "UNKNOWN":
                explainable += rc.estimated_lost_intents or 0

        total = report.total_estimated_lost_intents
        explained = min(explainable, total)
        unexplained = max(0, total - explained)

        return (
            report.model_copy(
                update={
                    "root_causes": causes,
                    "explained_lost_intents": explained,
                    "unexplained_lost_intents": unexplained,
                }
            ),
            notes,
        )

    # ------------------------------------------------------------------
    # Step 1: dataset validation
    # ------------------------------------------------------------------

    def _validate_dataset(self, dataset_ref: str) -> tuple[list[str], bool]:
        """Run data quality checks via the analytics source.

        The DuckDB source applies its own thresholds (e.g. 5% null-rate),
        so we defer entirely to its ``ok`` flag and ``warnings`` list rather
        than re-checking with a potentially conflicting threshold.
        """
        result = self._source.validate_dataset(dataset_ref)
        return list(result.warnings), result.ok

    # ------------------------------------------------------------------
    # Step 2: tool pipeline
    # ------------------------------------------------------------------

    def _run_tool_pipeline(
        self, dataset_ref: str
    ) -> tuple[EvidenceLedger, list[str], str, list[ToolResult]]:
        """Execute the fixed 6-tool pipeline and return its trace details."""
        tools = build_default_tools(self._source, self._artifacts)
        registry = ToolRegistry()
        for t in tools:
            registry.register(t)

        policy = ToolPolicy()
        ledger = EvidenceLedger(prefix=self._evidence_code_prefix)
        tool_results: list[ToolResult] = []
        call_idx = 0

        # 2a. get_payment_funnel (always)
        funnel_res = registry.execute(
            self._call_id(call_idx), "get_payment_funnel", policy, dataset_ref=dataset_ref
        )
        call_idx += 1
        ledger.record_result(funnel_res)
        tool_results.append(funnel_res)
        anomalous_stages = [
            e.metrics["stage"]
            for e in funnel_res.evidence
            if isinstance(e.metrics.get("stage"), str)
        ]
        funnel_summary = funnel_res.summary

        # 2b. analyze_benefit_gap (always — self-detects friction)
        benefit_res = registry.execute(
            self._call_id(call_idx), "analyze_benefit_gap", policy, dataset_ref=dataset_ref
        )
        call_idx += 1
        ledger.record_result(benefit_res)
        tool_results.append(benefit_res)

        # 2c. inspect_payment_events (always — self-detects timeouts)
        inspect_res = registry.execute(
            self._call_id(call_idx), "inspect_payment_events", policy, dataset_ref=dataset_ref
        )
        call_idx += 1
        ledger.record_result(inspect_res)
        tool_results.append(inspect_res)

        # 2d. trace_cancel_and_reorder (always — self-detects cancel flow changes)
        cancel_res = registry.execute(
            self._call_id(call_idx), "trace_cancel_and_reorder", policy, dataset_ref=dataset_ref
        )
        call_idx += 1
        ledger.record_result(cancel_res)
        tool_results.append(cancel_res)

        # 2e. get_config_changes (always — self-detects relevant config changes)
        config_res = registry.execute(
            self._call_id(call_idx), "get_config_changes", policy, dataset_ref=dataset_ref
        )
        call_idx += 1
        ledger.record_result(config_res)
        tool_results.append(config_res)

        # 2f. breakdown_conversion_loss — only when anomalous stages exist
        #     (plan: "定位异常阶段 → breakdown_conversion_loss").
        if anomalous_stages:
            for dim in self._dimensions:
                breakdown_res = registry.execute(
                    self._call_id(call_idx),
                    "breakdown_conversion_loss",
                    policy,
                    dataset_ref=dataset_ref,
                    dimension=dim,
                )
                call_idx += 1
                ledger.record_result(breakdown_res)
                tool_results.append(breakdown_res)

        return ledger, anomalous_stages, funnel_summary, tool_results

    # ------------------------------------------------------------------
    # Step 4: generate + validate + retry
    # ------------------------------------------------------------------

    def _generate_with_retry(
        self, context: DiagnosisContext
    ) -> tuple[DiagnosisReport, list[ValidationIssue]]:
        """Run adapter → validator in a loop, allowing up to _max_retries corrections.

        For the M2 deterministic RuleBasedModelAdapter, the retry produces the
        same output on every iteration; the correction loop primarily exists as
        a structural placeholder for future LLM adapters that can self-correct
        based on validation feedback.
        """
        report: DiagnosisReport | None = None
        issues: list[ValidationIssue] = []

        for attempt in range(self._max_retries + 1):
            report = self._adapter.generate(context)
            issues = self._validator.validate(report, context)
            retryable = [i for i in issues if i.retryable]

            if not retryable:
                # No retryable issues — report is as valid as we can make it.
                break

            if attempt < self._max_retries:
                # Re-build context with validation feedback so the adapter can
                # (in principle) correct its output on the next iteration.
                context = _augment_context_with_issues(context, retryable)

        if report is None:
            raise OrchestratorFailure("no report generated after retries")
        return report, issues

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _call_id(idx: int) -> str:
        return f"c{idx}"


def _augment_context_with_issues(
    context: DiagnosisContext, issues: list[ValidationIssue]
) -> DiagnosisContext:
    """Append validation issues as evidence summaries for the correction retry.

    This lets the adapter (especially future LLM adapters) see what was wrong
    and attempt correction. The original context is immutable, so we create a
    new instance with augmented summaries.
    """
    feedback_lines = [f"VALIDATION_FEEDBACK: {i.code} [{i.field}] {i.message}" for i in issues]
    return context.model_copy(
        update={"evidence_summaries": context.evidence_summaries + feedback_lines}
    )
