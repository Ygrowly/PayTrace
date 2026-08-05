"""DiagnosisOrchestrator — fixed 4-step workflow (plan § 14.1).

Ties together DuckDBAnalyticsSource, ToolRegistry, EvidenceLedger,
ContextBuilder, ModelAdapter, ReportValidator, and one correction retry
into a single synchronous pipeline.

No Celery, no DB persistence, no SSE — those are M2b/M2c concerns.
"""

import uuid
from dataclasses import dataclass

from app.analytics.base import PaymentAnalyticsSource
from app.diagnosis.adapter import RuleBasedModelAdapter
from app.diagnosis.context import ContextBuilder
from app.diagnosis.model import DiagnosisContext, ModelAdapter
from app.diagnosis.report import DiagnosisReport
from app.diagnosis.validator import ReportValidator, ValidationIssue
from app.harness.artifact_store import ArtifactStore
from app.tools.base import EvidenceLedger, ToolPolicy, ToolRegistry, ToolResult
from app.tools.diagnostic import build_default_tools

_DEFAULT_DIMENSIONS = ("payment_channel", "payment_method")


class OrchestratorFailure(Exception):
    """Raised when the orchestrator cannot produce a valid report."""


@dataclass
class DiagnosisExecution:
    """A report plus the trace needed by API and evaluation consumers.

    ``run()`` intentionally keeps returning only ``DiagnosisReport`` for the
    M2 callers. M3 consumers use this richer result so scoring and the UI can
    inspect system-produced evidence and tool timings without re-running the
    diagnostic workflow or putting business calculations in the frontend.
    """

    report: DiagnosisReport
    ledger: EvidenceLedger
    tool_results: tuple[ToolResult, ...]
    validation_issues: tuple[ValidationIssue, ...]


class DiagnosisOrchestrator:
    """Fixed workflow orchestrator for the diagnosis pipeline.

    Workflow (plan § 14.1):

    1. Validate dataset → data quality checks
    2. Execute fixed tool pipeline:
       get_payment_funnel → breakdown_conversion_loss
       → analyze_benefit_gap → inspect_payment_events
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
    ) -> None:
        self._source = source
        self._artifacts = artifacts
        self._adapter = adapter or RuleBasedModelAdapter()
        self._validator = validator or ReportValidator()
        self._dimensions = dimensions
        self._max_retries = max_retries
        self._evidence_code_prefix = evidence_code_prefix

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

        The additional trace is produced by the same fixed workflow as
        :meth:`run`; it is not a second or evaluation-only diagnostic path.
        """
        iid = incident_id or f"inc-{uuid.uuid4().hex[:12]}"
        rid = diagnosis_run_id or f"run-{uuid.uuid4().hex[:12]}"

        # Step 1: validate dataset
        missing_data, _ = self._validate_dataset(dataset_ref)

        # Step 2: execute tool pipeline
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

        # Only raise for truly blocking non-retryable issues (e.g. schema
        # version mismatch, structural violations).  Warning-level issues
        # (R11_BENEFIT_ONLY — "not an error, but recorded as a warning")
        # are returned alongside the report so callers can inspect them.
        blocking = [i for i in issues if not i.retryable and i.code.startswith(("R12", "R3"))]
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
        """Execute the fixed-4-tool pipeline and return its trace details."""
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

        # 2d. breakdown_conversion_loss — only when anomalous stages exist
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
