"""DiagnosticHarness — the governed investigation loop (notes § 8).

The harness owns the incident scope, the tool set, the budget, and the stop
conditions. A policy decides *what to do next*; the harness decides *what is
allowed* and records everything that happened.

The investigation produces evidence; it does not write the report. Report
generation stays in ``DiagnosisOrchestrator`` so the B0 fixed pipeline and the
B2 investigation are compared with the report step held constant.
"""

from dataclasses import dataclass, field
from typing import Any

from app.analytics.base import PaymentAnalyticsSource
from app.harness.artifact_store import ArtifactStore
from app.harness.hooks import (
    ArtifactHook,
    Budget,
    BudgetHook,
    CapabilityBundleHook,
    EarlyExitHook,
    EvidencePolicyHook,
    EvidenceRegistrationHook,
    HookChain,
    HypothesisResolutionHook,
    IncidentScopeHook,
    RejectedHypothesisHook,
    SchemaValidationHook,
    ToolCallBlocked,
    ToolCallContext,
    ToolStatusHook,
)
from app.harness.investigation import (
    InvestigationPolicy,
    InvestigationState,
    ScriptedInvestigationPolicy,
    call_signature,
)
from app.harness.ledger import Hypothesis, HypothesisLedger
from app.harness.routing import CapabilityBundle, route_capabilities
from app.tools.base import EvidenceLedger, ToolPolicy, ToolRegistry, ToolResult
from app.tools.diagnostic import build_default_tools

DEFAULT_MAX_TOOL_CALLS = 8
# Bounded so a policy that keeps proposing illegal calls cannot spin forever.
_MAX_BLOCKED_ATTEMPTS = 3

_TRIAGE_TOOL = "get_payment_funnel"


class HarnessFailure(Exception):
    """Raised when the investigation cannot even be scoped."""


@dataclass
class HarnessResult:
    """Investigation outcome, in the shape the orchestrator consumes."""

    ledger: EvidenceLedger
    tool_results: tuple[ToolResult, ...]
    hypotheses: tuple[Hypothesis, ...]
    anomalous_stages: list[str]
    funnel_summary: str
    missing_data: list[str]
    incident_scope: dict[str, Any]
    bundle: CapabilityBundle
    early_exit_reason: str | None
    steps: list[dict[str, Any]] = field(default_factory=list)
    blocked_calls: list[dict[str, Any]] = field(default_factory=list)
    degradations: list[str] = field(default_factory=list)
    policy_name: str = "ScriptedInvestigationPolicy"
    policy_model_name: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class DiagnosticHarness:
    """Runs a governed, multi-step investigation over one incident dataset."""

    def __init__(
        self,
        source: PaymentAnalyticsSource,
        *,
        artifacts: ArtifactStore | None = None,
        policy: InvestigationPolicy | None = None,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
        evidence_code_prefix: str = "",
    ) -> None:
        self._source = source
        self._artifacts = artifacts
        self._policy: InvestigationPolicy = policy or ScriptedInvestigationPolicy()
        self._max_tool_calls = max_tool_calls
        self._evidence_code_prefix = evidence_code_prefix

    # ------------------------------------------------------------------

    def run(
        self,
        dataset_ref: str,
        *,
        incident_id: str,
        diagnosis_run_id: str,
        scenario_id: str = "",
    ) -> HarnessResult:
        budget = Budget(max_calls=self._max_tool_calls)
        registry = ToolRegistry()
        for tool in build_default_tools(self._source, self._artifacts):
            registry.register(tool)

        evidence = EvidenceLedger(prefix=self._evidence_code_prefix)
        hypotheses = HypothesisLedger()
        tool_policy = ToolPolicy(max_calls=self._max_tool_calls)

        # Hook instances are shared across the triage chain and the loop chain
        # so their accumulated state can be read once at the end.
        artifact_hook = ArtifactHook()
        status_hook = ToolStatusHook()
        early_exit = EarlyExitHook(hypotheses, budget)

        tool_results: list[ToolResult] = []
        steps: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        called_signatures: list[str] = [call_signature(_TRIAGE_TOOL, {})]
        call_idx = 0

        # --- 1. Triage: scope the incident before any routing happens --------
        # The bundle cannot exist yet — it is derived from this call's result.
        triage_chain = HookChain(
            before=[
                IncidentScopeHook(dataset_ref),
                SchemaValidationHook(),
                BudgetHook(budget),
                EvidencePolicyHook(tool_policy, registry),
            ],
            after=[EvidenceRegistrationHook(evidence, hypotheses), artifact_hook, status_hook],
        )
        funnel_result = self._invoke(
            registry,
            budget,
            triage_chain,
            ToolCallContext(tool_name=_TRIAGE_TOOL, arguments={"dataset_ref": dataset_ref}, step=0),
            dataset_ref=dataset_ref,
            call_idx=call_idx,
        )
        call_idx += 1
        tool_results.append(funnel_result)

        anomalous_stages = [
            e.metrics["stage"]
            for e in funnel_result.evidence
            if isinstance(e.metrics.get("stage"), str)
        ]
        missing_data, _ = self._validate_dataset(dataset_ref)
        scope = {
            "incident_id": incident_id,
            "diagnosis_run_id": diagnosis_run_id,
            "scenario_id": scenario_id,
        }
        steps.append(
            {
                "step": 0,
                "tool": _TRIAGE_TOOL,
                "hypothesis": None,
                "status": funnel_result.status,
                "reasoning": "incident triage and scoping",
                "blocked": None,
            }
        )

        # --- 2. Route capabilities from the triage signals -------------------
        bundle = route_capabilities(anomalous_stages=anomalous_stages, missing_data=missing_data)

        # --- 3. Raise the initial hypotheses ---------------------------------
        propose = getattr(self._policy, "propose_hypotheses", None)
        if callable(propose):
            propose(hypotheses, bundle.signals)

        # --- 4. Investigation loop ------------------------------------------
        loop_chain = HookChain(
            before=[
                CapabilityBundleHook(bundle),
                IncidentScopeHook(dataset_ref),
                SchemaValidationHook(),
                BudgetHook(budget),
                RejectedHypothesisHook(hypotheses),
                EvidencePolicyHook(tool_policy, registry),
            ],
            after=[
                EvidenceRegistrationHook(evidence, hypotheses),
                HypothesisResolutionHook(hypotheses),
                artifact_hook,
                status_hook,
                early_exit,
            ],
        )

        while True:
            state = self._build_state(
                scope=scope,
                bundle=bundle,
                hypotheses=hypotheses,
                evidence=evidence,
                budget=budget,
                anomalous_stages=anomalous_stages,
                missing_data=missing_data,
                called_tools=[r.tool_name for r in tool_results],
                called_signatures=called_signatures,
                blocked_attempts=blocked,
            )
            action = self._policy.decide(state)

            if action.kind == "finish" or not action.tool_name:
                steps.append(
                    {
                        "step": len(steps),
                        "tool": None,
                        "hypothesis": None,
                        "status": "finish",
                        "reasoning": action.reasoning,
                        "blocked": None,
                    }
                )
                break

            ctx = ToolCallContext(
                tool_name=action.tool_name,
                # dataset_ref is injected here; a policy-supplied value is
                # discarded so a model cannot point a tool at another incident.
                arguments={**action.arguments, "dataset_ref": dataset_ref},
                step=len(steps),
                hypothesis_id=action.hypothesis_id,
            )
            try:
                result = self._invoke(
                    registry,
                    budget,
                    loop_chain,
                    ctx,
                    dataset_ref=dataset_ref,
                    call_idx=call_idx,
                )
            except ToolCallBlocked as exc:
                blocked.append(
                    {
                        "tool": action.tool_name,
                        "hypothesis": action.hypothesis_id,
                        "code": exc.code,
                        "message": str(exc),
                    }
                )
                steps.append(
                    {
                        "step": len(steps),
                        "tool": action.tool_name,
                        "hypothesis": action.hypothesis_id,
                        "status": "blocked",
                        "reasoning": action.reasoning,
                        "blocked": exc.code,
                    }
                )
                if len(blocked) >= _MAX_BLOCKED_ATTEMPTS:
                    break
                continue

            call_idx += 1
            tool_results.append(result)
            called_signatures.append(
                call_signature(
                    action.tool_name,
                    {k: v for k, v in action.arguments.items() if k != "dataset_ref"},
                )
            )
            steps.append(
                {
                    "step": len(steps),
                    "tool": action.tool_name,
                    "hypothesis": action.hypothesis_id,
                    "status": result.status,
                    "reasoning": action.reasoning,
                    "blocked": None,
                    "evidence_count": len(result.evidence),
                }
            )

            if early_exit.stop_reason is not None:
                break

        fallback_reason = getattr(self._policy, "fallback_reason", None)

        # Close out anything the investigation never reached. Leaving an open
        # question dangling would let the ledger read as "unresolved" when the
        # run is over; recording it as NEEDS_DATA is a fact about the run.
        for hypothesis in hypotheses.open_hypotheses():
            hypotheses.resolve(
                hypothesis.hypothesis_id,
                "NEEDS_DATA",
                reason="investigation ended before this hypothesis could be tested",
            )

        return HarnessResult(
            ledger=evidence,
            tool_results=tuple(tool_results),
            hypotheses=tuple(hypotheses.all()),
            anomalous_stages=anomalous_stages,
            funnel_summary=funnel_result.summary,
            missing_data=missing_data,
            incident_scope=scope,
            bundle=bundle,
            early_exit_reason=early_exit.stop_reason or "POLICY_FINISHED",
            steps=steps,
            blocked_calls=blocked,
            degradations=list(artifact_hook.degradations) + list(status_hook.partials),
            policy_name=type(self._policy).__name__,
            policy_model_name=getattr(self._policy, "model_name", None),
            fallback_used=bool(getattr(self._policy, "fallback_used", False)),
            fallback_reason=fallback_reason,
            input_tokens=(getattr(self._policy, "last_usage", None) or {}).get("input_tokens"),
            output_tokens=(getattr(self._policy, "last_usage", None) or {}).get("output_tokens"),
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _invoke(
        registry: ToolRegistry,
        budget: Budget,
        chain: HookChain,
        ctx: ToolCallContext,
        *,
        dataset_ref: str,
        call_idx: int,
    ) -> ToolResult:
        """Run one tool call through the hook chain.

        ``dataset_ref`` is stripped from the arguments the tool receives only
        after the hooks have seen it, so the scope hook validates the effective
        target rather than a value the caller could omit.
        """
        chain.before_call(ctx)
        arguments = {k: v for k, v in ctx.arguments.items() if k != "dataset_ref"}
        result = registry.execute(
            f"c{call_idx}", ctx.tool_name, None, dataset_ref=dataset_ref, **arguments
        )
        budget.consume()
        chain.after_call(ctx, result)
        return result

    def _validate_dataset(self, dataset_ref: str) -> tuple[list[str], bool]:
        result = self._source.validate_dataset(dataset_ref)
        return list(result.warnings), result.ok

    @staticmethod
    def _build_state(
        *,
        scope: dict[str, Any],
        bundle: CapabilityBundle,
        hypotheses: HypothesisLedger,
        evidence: EvidenceLedger,
        budget: Budget,
        anomalous_stages: list[str],
        missing_data: list[str],
        called_tools: list[str],
        called_signatures: list[str],
        blocked_attempts: list[dict[str, Any]],
    ) -> InvestigationState:
        return InvestigationState(
            incident_scope=scope,
            allowed_tools=tuple(sorted(bundle.allowed_tools)),
            preferred_first=bundle.preferred_first,
            signals=bundle.signals,
            localized_stages=list(anomalous_stages),
            observed_loss=_observed_loss(evidence),
            evidence_summaries=evidence.summaries(),
            hypotheses=hypotheses.all(),
            rejected_hypotheses=hypotheses.rejected_types(),
            missing_data=list(missing_data),
            remaining_budget=budget.remaining,
            called_tools=list(called_tools),
            called_signatures=list(called_signatures),
            blocked_attempts=[b["code"] for b in blocked_attempts],
        )


def _observed_loss(evidence: EvidenceLedger) -> int:
    """Total loss the evidence so far attributes, for the policy's context."""
    return int(
        sum(
            e.metrics.get("estimated_lost_intents", 0)
            for e in evidence.all()
            if isinstance(e.metrics.get("estimated_lost_intents"), int | float)
        )
    )
