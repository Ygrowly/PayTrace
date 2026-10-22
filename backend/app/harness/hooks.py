"""Before/After Tool hook chain (notes § 8.1).

The harness does not trust the model to stay in bounds. Every tool call passes
through this chain, and the chain's failure semantics are matched to the cost of
the operation:

* **Write side — block.** An out-of-bundle tool, a query against another
  incident's dataset, an exhausted budget, or a repeat of an already-rejected
  line of investigation is refused before it runs.
* **Read side — degrade.** If a large result cannot be offloaded to an artifact,
  the call still returns: the summary passes through and the run is marked as
  degraded rather than failing the whole diagnosis.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.harness.ledger import HypothesisLedger, evaluate_hypothesis, is_designated_probe
from app.harness.routing import CapabilityBundle
from app.tools.base import EvidenceLedger, ToolPolicy, ToolResult
from app.tools.schemas import validate_arguments


class ToolCallBlocked(Exception):
    """Raised by a Before-Tool hook to refuse a call before it executes."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class ToolCallContext:
    """Everything a hook needs to judge one proposed tool call."""

    tool_name: str
    arguments: dict[str, Any]
    step: int
    hypothesis_id: str | None = None


@dataclass
class Budget:
    """Tool-call and step budget for one investigation (notes § 8.6)."""

    max_calls: int = 8
    calls_used: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.max_calls - self.calls_used)

    @property
    def exhausted(self) -> bool:
        return self.remaining == 0

    def consume(self) -> None:
        self.calls_used += 1


class BeforeToolHook(Protocol):
    name: str

    def check(self, ctx: ToolCallContext) -> None: ...


class AfterToolHook(Protocol):
    name: str

    def observe(self, ctx: ToolCallContext, result: ToolResult) -> None: ...


# --- Before-Tool hooks -------------------------------------------------------


class CapabilityBundleHook:
    """Refuses tools outside the incident's routed capability bundle."""

    name = "capability_bundle"

    def __init__(self, bundle: CapabilityBundle) -> None:
        self._bundle = bundle

    def check(self, ctx: ToolCallContext) -> None:
        if not self._bundle.allows(ctx.tool_name):
            raise ToolCallBlocked(
                "TOOL_NOT_IN_BUNDLE",
                f"{ctx.tool_name} is not in the capability bundle " f"({self._bundle.rationale})",
            )


class IncidentScopeHook:
    """Refuses queries against a dataset other than the incident's own."""

    name = "incident_scope"

    def __init__(self, dataset_ref: str) -> None:
        self._dataset_ref = dataset_ref

    def check(self, ctx: ToolCallContext) -> None:
        requested = ctx.arguments.get("dataset_ref")
        if requested is not None and requested != self._dataset_ref:
            raise ToolCallBlocked(
                "OUT_OF_INCIDENT_SCOPE",
                f"{ctx.tool_name} requested a dataset outside this incident",
            )


class BudgetHook:
    """Refuses calls once the investigation budget is spent."""

    name = "budget"

    def __init__(self, budget: Budget) -> None:
        self._budget = budget

    def check(self, ctx: ToolCallContext) -> None:
        if self._budget.exhausted:
            raise ToolCallBlocked(
                "BUDGET_EXHAUSTED", f"tool call budget exhausted ({self._budget.max_calls})"
            )


class SchemaValidationHook:
    """Validates tool arguments against the tool's declared schema.

    Rejects a call whose arguments are malformed, unknown, or out of range
    before any data is touched — the model does not get to define what a tool
    accepts.
    """

    name = "schema_validation"

    def check(self, ctx: ToolCallContext) -> None:
        arguments = {k: v for k, v in ctx.arguments.items() if k != "dataset_ref"}
        problem = validate_arguments(ctx.tool_name, arguments)
        if problem is not None:
            raise ToolCallBlocked("SCHEMA_INVALID", f"{ctx.tool_name}: {problem}")


class EvidencePolicyHook:
    """Applies the existing ToolPolicy: read-only, budget, and de-duplication."""

    name = "evidence_policy"

    def __init__(self, policy: ToolPolicy, registry: Any) -> None:
        self._policy = policy
        self._registry = registry

    def check(self, ctx: ToolCallContext) -> None:
        tool = self._registry.get(ctx.tool_name)
        kwargs = {k: v for k, v in ctx.arguments.items()}
        try:
            self._policy.before_call(tool, kwargs)
        except Exception as exc:  # ToolPolicyViolation and friends
            raise ToolCallBlocked("POLICY_VIOLATION", str(exc)) from exc


class RejectedHypothesisHook:
    """Refuses to re-investigate an explanation its own evidence ruled out."""

    name = "rejected_hypothesis"

    def __init__(self, hypotheses: HypothesisLedger) -> None:
        self._hypotheses = hypotheses

    def check(self, ctx: ToolCallContext) -> None:
        if ctx.hypothesis_id is None:
            return
        hypothesis = self._hypotheses.get(ctx.hypothesis_id)
        if hypothesis is not None and hypothesis.status == "REJECTED":
            raise ToolCallBlocked(
                "HYPOTHESIS_REJECTED",
                f"{ctx.hypothesis_id} ({hypothesis.root_cause_type}) was rejected: "
                f"{hypothesis.rejection_reason or 'no reason recorded'}",
            )


# --- After-Tool hooks --------------------------------------------------------


class EvidenceRegistrationHook:
    """Registers the call's evidence and links it to the hypothesis it served."""

    name = "evidence_registration"

    def __init__(self, evidence: EvidenceLedger, hypotheses: HypothesisLedger) -> None:
        self._evidence = evidence
        self._hypotheses = hypotheses
        self.registered_codes: list[str] = []

    def observe(self, ctx: ToolCallContext, result: ToolResult) -> None:
        recorded = self._evidence.record_result(result)
        codes = [e.evidence_code for e in recorded]
        self.registered_codes.extend(codes)

        if ctx.hypothesis_id is None or not codes:
            return
        hypothesis = self._hypotheses.get(ctx.hypothesis_id)
        if hypothesis is None or hypothesis.status in ("REJECTED", "SUPPORTED", "PARTIAL"):
            return
        for code in codes:
            self._hypotheses.record_evidence(ctx.hypothesis_id, code, supports=True)


class ArtifactHook:
    """Verifies large results were offloaded; degrades instead of blocking.

    A missing artifact ref is a capability loss (the raw rows are gone), not an
    integrity failure — the run continues on the summary and is marked degraded.
    """

    name = "artifact"

    def __init__(self) -> None:
        self.degradations: list[str] = []

    def observe(self, ctx: ToolCallContext, result: ToolResult) -> None:
        if result.artifact_ref is None and result.row_count > 0:
            self.degradations.append(
                f"{result.tool_name} ({result.tool_call_id}) returned {result.row_count} rows "
                f"without an artifact; continuing on the summary only"
            )


class ToolStatusHook:
    """Records partial/failed tool outcomes so the report can qualify itself."""

    name = "tool_status"

    def __init__(self) -> None:
        self.failures: list[str] = []
        self.partials: list[str] = []

    def observe(self, ctx: ToolCallContext, result: ToolResult) -> None:
        if result.status == "failed":
            self.failures.append(f"{result.tool_name}: {result.summary}")
        elif result.status == "partial":
            self.partials.append(f"{result.tool_name}: {result.summary}")


class HypothesisResolutionHook:
    """Moves a hypothesis to a terminal state once its probe has spoken.

    Only a designated probe can rule a hypothesis out — a generic drilldown
    that returns nothing must not be read as evidence of absence.
    """

    name = "hypothesis_resolution"

    def __init__(self, hypotheses: HypothesisLedger) -> None:
        self._hypotheses = hypotheses
        self.resolutions: list[str] = []

    def observe(self, ctx: ToolCallContext, result: ToolResult) -> None:
        if ctx.hypothesis_id is None:
            return
        hypothesis = self._hypotheses.get(ctx.hypothesis_id)
        if hypothesis is None or hypothesis.status not in ("PROPOSED", "INVESTIGATING"):
            return

        produced = {draft.evidence_type for draft in result.evidence}
        probe_completed = result.status == "success" and is_designated_probe(
            ctx.tool_name, hypothesis.root_cause_type
        )
        decision = evaluate_hypothesis(
            hypothesis.root_cause_type, produced, probe_completed=probe_completed
        )
        if decision is None:
            return

        status, reason = decision
        resolved = self._hypotheses.resolve(ctx.hypothesis_id, status, reason=reason)
        self.resolutions.append(f"{resolved.hypothesis_id} {resolved.root_cause_type} -> {status}")


class EarlyExitHook:
    """Decides when further tool calls cannot change the conclusion."""

    name = "early_exit"

    _CONCLUSIVE = ("SUPPORTED", "PARTIAL")

    def __init__(self, hypotheses: HypothesisLedger, budget: Budget) -> None:
        self._hypotheses = hypotheses
        self._budget = budget
        self.stop_reason: str | None = None

    def observe(self, ctx: ToolCallContext, result: ToolResult) -> None:
        if self.stop_reason is not None:
            return
        if self._budget.exhausted:
            self.stop_reason = "BUDGET_EXHAUSTED"
            return
        if result.status == "failed" and not self._hypotheses.open_hypotheses():
            self.stop_reason = "NO_OPEN_HYPOTHESES"
            return
        open_hypotheses = self._hypotheses.open_hypotheses()
        if not open_hypotheses:
            resolved = {h.status for h in self._hypotheses.all()}
            if resolved and resolved <= set(self._CONCLUSIVE) | {"REJECTED", "NEEDS_DATA"}:
                self.stop_reason = "ALL_HYPOTHESES_RESOLVED"


# --- Chain -------------------------------------------------------------------


@dataclass
class HookChain:
    """Ordered Before/After hooks applied to every tool call."""

    before: list[BeforeToolHook] = field(default_factory=list)
    after: list[AfterToolHook] = field(default_factory=list)

    def before_call(self, ctx: ToolCallContext) -> None:
        for hook in self.before:
            hook.check(ctx)

    def after_call(self, ctx: ToolCallContext, result: ToolResult) -> None:
        for hook in self.after:
            hook.observe(ctx, result)
