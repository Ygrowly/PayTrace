"""Investigation policies — how the harness decides what to do next (notes § 8).

The policy chooses the next action; it never computes a metric or invents
evidence. Two implementations:

* :class:`ScriptedInvestigationPolicy` — deterministic, no API key. Drives CI,
  the no-model demo, and the fallback path.
* :class:`OpenAIToolCallingPolicy` — a real tool-calling model, falling back to
  the scripted policy (with an explicit reason) when the model is unavailable.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.harness.ledger import Hypothesis, HypothesisLedger
from app.tools.schemas import tool_schemas

logger = logging.getLogger(__name__)

INVESTIGATION_PROMPT_VERSION = "investigation_v1"

# Root cause the scripted policy raises for each routed signal.
_HYPOTHESIS_BY_SIGNAL: dict[str, str] = {
    "DATA_INTEGRITY": "DATA_QUALITY_ISSUE",
    "AUTH_FAILURE": "AUTHENTICATION_FAILURE",
    "CHANNEL_TIMEOUT": "CHANNEL_TIMEOUT",
    "CALLBACK_ANOMALY": "CALLBACK_FAILURE",
    "DECISION_FRICTION": "BENEFIT_SELECTION_FRICTION",
    "UNKNOWN": "UNKNOWN",
}

# Tool -> the root cause it is the designated probe for.
_PROBE_TARGET: dict[str, str] = {
    "inspect_payment_events": "CHANNEL_TIMEOUT",
    "analyze_benefit_gap": "BENEFIT_SELECTION_FRICTION",
}

_BREAKDOWN_DIMENSIONS = ("payment_channel", "payment_method")


@dataclass
class InvestigationState:
    """What the policy is allowed to know at each step (notes § 8.3).

    Deliberately excludes Ground Truth, raw event rows, and any hint of the
    scenario kind — the policy investigates what the tools returned.
    """

    incident_scope: dict[str, Any]
    allowed_tools: tuple[str, ...]
    preferred_first: tuple[str, ...]
    signals: tuple[str, ...]
    localized_stages: list[str] = field(default_factory=list)
    observed_loss: int = 0
    evidence_summaries: list[str] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    rejected_hypotheses: dict[str, str] = field(default_factory=dict)
    missing_data: list[str] = field(default_factory=list)
    remaining_budget: int = 0
    called_tools: list[str] = field(default_factory=list)
    # Tool + arguments already executed, so a repeatable tool (the dimension
    # breakdown) is not issued twice for the same arguments.
    called_signatures: list[str] = field(default_factory=list)
    blocked_attempts: list[str] = field(default_factory=list)


class InvestigationAction(BaseModel):
    """The policy's next move: call a tool, or stop."""

    kind: Literal["tool_call", "finish"]
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    hypothesis_id: str | None = None
    reasoning: str = ""


class InvestigationPolicy(Protocol):
    """Chooses the next investigation step from the current state."""

    def decide(self, state: InvestigationState) -> InvestigationAction: ...


# ---------------------------------------------------------------------------
# Deterministic policy
# ---------------------------------------------------------------------------


class ScriptedInvestigationPolicy:
    """Deterministic hypothesis-driven investigation.

    It raises one hypothesis per routed signal, then probes them in the bundle's
    priority order, binding each call to the hypothesis it tests. When the plan
    is exhausted — or every hypothesis is already terminal — it stops.

    Stateless on purpose: the next step is re-derived from the state on every
    call, so one instance can serve many runs — the fallback path inside
    :class:`OpenAIToolCallingPolicy` would otherwise leak an exhausted plan
    between scenarios.

    This is not the fixed pipeline under a new name: the tool list comes from
    the routed bundle (which varies by incident), calls are bound to hypotheses,
    and a call whose hypothesis was already rejected is never issued.
    """

    def decide(self, state: InvestigationState) -> InvestigationAction:
        if not state.hypotheses:
            return InvestigationAction(
                kind="finish",
                reasoning="no hypotheses to test",
            )

        # Stop as soon as nothing further can change the conclusion.
        if not any(h.status in ("PROPOSED", "INVESTIGATING") for h in state.hypotheses):
            return InvestigationAction(kind="finish", reasoning="all hypotheses resolved")

        for tool_name, arguments in self._build_plan(state):
            hypothesis = self._bind(tool_name, state)
            if hypothesis is None:
                continue
            return InvestigationAction(
                kind="tool_call",
                tool_name=tool_name,
                arguments=arguments,
                hypothesis_id=hypothesis.hypothesis_id,
                reasoning=f"tests {hypothesis.root_cause_type} via {tool_name}",
            )

        return InvestigationAction(kind="finish", reasoning="investigation plan exhausted")

    def _build_plan(self, state: InvestigationState) -> list[tuple[str, dict[str, Any]]]:
        # A clean incident with no localized stage and no data gap has nothing to
        # drill into: more calls cannot change the conclusion, and running every
        # drilldown anyway would surface sampling noise as a false positive.
        if not state.localized_stages and not state.missing_data:
            return []

        plan: list[tuple[str, dict[str, Any]]] = []
        for tool in state.preferred_first:
            if tool not in state.allowed_tools:
                continue
            if tool == "breakdown_conversion_loss":
                # Repeatable per dimension, so it is tracked by signature.
                for dimension in _BREAKDOWN_DIMENSIONS:
                    candidate = {"dimension": dimension}
                    if call_signature(tool, candidate) not in state.called_signatures:
                        plan.append((tool, candidate))
            elif tool not in state.called_tools:
                plan.append((tool, {}))
        return plan

    @staticmethod
    def _bind(tool_name: str, state: InvestigationState) -> Hypothesis | None:
        target = _PROBE_TARGET.get(tool_name)
        open_hypotheses = [h for h in state.hypotheses if h.status in ("PROPOSED", "INVESTIGATING")]
        if not open_hypotheses:
            return None
        if target is not None:
            for hypothesis in open_hypotheses:
                if hypothesis.root_cause_type == target:
                    return hypothesis
        return open_hypotheses[0]

    def propose_hypotheses(self, ledger: HypothesisLedger, signals: tuple[str, ...]) -> None:
        """Raise the initial hypotheses for this incident's signals."""
        for signal in signals:
            root_cause = _HYPOTHESIS_BY_SIGNAL.get(signal)
            if root_cause is None:
                continue
            ledger.propose(root_cause, required_next_tool=_probe_for(root_cause))


def _probe_for(root_cause: str) -> str | None:
    for tool, target in _PROBE_TARGET.items():
        if target == root_cause:
            return tool
    return None


def call_signature(tool_name: str, arguments: dict[str, Any]) -> str:
    """Stable identity for one tool call, used to skip repeats."""
    return f"{tool_name}:{json.dumps(arguments, sort_keys=True)}"


# ---------------------------------------------------------------------------
# Model-backed policy
# ---------------------------------------------------------------------------

INVESTIGATION_SYSTEM_PROMPT = (
    "You are investigating a payment conversion anomaly.\n"
    "\n"
    "You may call only the tools provided. Every call must serve an open\n"
    "hypothesis from the list you are given; never call a tool that is not in\n"
    "the allowed list, and never re-investigate a hypothesis that was already\n"
    "rejected while it has no new evidence.\n"
    "\n"
    "Tool results are summaries. Evidence codes come from the system, not from\n"
    "you — do not invent codes, metric values, or root cause labels.\n"
    "\n"
    "Stop as soon as the evidence cannot change the conclusion. Call no tool\n"
    "and stop when the budget is exhausted or every hypothesis is resolved.\n"
)


class OpenAIToolCallingPolicy:
    """Tool-calling model policy, with a scripted fallback.

    The fallback is explicit and observable: ``fallback_used`` and
    ``fallback_reason`` are surfaced so a run is never reported as a successful
    model investigation when the model was not actually reached.
    """

    def __init__(
        self,
        *,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        timeout: float = 60.0,
        prompt_version: str = INVESTIGATION_PROMPT_VERSION,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self.prompt_version = prompt_version
        self.fallback_used = False
        self.fallback_reason: str | None = None
        self.last_usage: dict[str, int] | None = None
        self._fallback = ScriptedInvestigationPolicy()

    @property
    def model_name(self) -> str:
        return self._model or "rule_based"

    def propose_hypotheses(self, ledger: HypothesisLedger, signals: tuple[str, ...]) -> None:
        self._fallback.propose_hypotheses(ledger, signals)

    def decide(self, state: InvestigationState) -> InvestigationAction:
        if not self._api_key or not self._base_url:
            return self._fall_back("MODEL_NOT_CONFIGURED", state)

        try:
            from openai import OpenAI

            client = OpenAI(base_url=self._base_url, api_key=self._api_key, timeout=self._timeout)
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": INVESTIGATION_SYSTEM_PROMPT},
                    {"role": "user", "content": _render_state(state)},
                ],
                tools=tool_schemas(list(state.allowed_tools)),
                tool_choice="auto",
                temperature=0.0,
            )
            usage = response.usage
            self.last_usage = {
                "input_tokens": usage.prompt_tokens if usage else 0,
                "output_tokens": usage.completion_tokens if usage else 0,
            }
            return self._parse(response, state)
        except Exception as exc:  # noqa: BLE001 - any model failure falls back
            logger.warning(
                "tool-calling policy failed (%s: %s), falling back to scripted",
                type(exc).__name__,
                str(exc)[:200],
            )
            return self._fall_back("MODEL_CALL_FAILED", state)

    # -- internals -----------------------------------------------------------

    def _fall_back(self, reason: str, state: InvestigationState) -> InvestigationAction:
        self.fallback_used = True
        self.fallback_reason = reason
        action = self._fallback.decide(state)
        return action.model_copy(
            update={"reasoning": f"[scripted fallback: {reason}] {action.reasoning}"}
        )

    def _parse(self, response: Any, state: InvestigationState) -> InvestigationAction:
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []
        if not tool_calls:
            return InvestigationAction(
                kind="finish",
                reasoning=(message.content or "model stopped")[:500],
            )

        call = tool_calls[0]
        try:
            arguments = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            return InvestigationAction(
                kind="finish",
                reasoning=f"model produced unparseable arguments: {call.function.arguments!r}",
            )
        if not isinstance(arguments, dict):
            arguments = {}

        return InvestigationAction(
            kind="tool_call",
            tool_name=call.function.name,
            arguments=arguments,
            hypothesis_id=_match_hypothesis(arguments.get("hypothesis_id"), state),
            reasoning=f"model requested {call.function.name}",
        )


def _match_hypothesis(requested: Any, state: InvestigationState) -> str | None:
    """Bind the model's chosen hypothesis, or the first open one."""
    open_hypotheses = [h for h in state.hypotheses if h.status in ("PROPOSED", "INVESTIGATING")]
    if isinstance(requested, str):
        for hypothesis in open_hypotheses:
            if hypothesis.hypothesis_id == requested:
                return hypothesis.hypothesis_id
    return open_hypotheses[0].hypothesis_id if open_hypotheses else None


def _render_state(state: InvestigationState) -> str:
    hypotheses = (
        "\n".join(f"- {h.hypothesis_id} [{h.status}] {h.root_cause_type}" for h in state.hypotheses)
        or "(none)"
    )
    rejected = "\n".join(f"- {k}: {v}" for k, v in state.rejected_hypotheses.items()) or "(none)"
    evidence = "\n".join(state.evidence_summaries[-20:]) or "(none)"
    return (
        f"## Incident scope\n{json.dumps(state.incident_scope, default=str)}\n\n"
        f"## Localized stages\n{', '.join(state.localized_stages) or '(none)'}\n\n"
        f"## Observed loss\n{state.observed_loss} purchase intents\n\n"
        f"## Hypotheses\n{hypotheses}\n\n"
        f"## Already rejected (do not re-investigate)\n{rejected}\n\n"
        f"## Evidence so far\n{evidence}\n\n"
        f"## Missing data\n{', '.join(state.missing_data) or '(none)'}\n\n"
        f"## Remaining tool budget\n{state.remaining_budget}\n\n"
        f"## Allowed tools\n{', '.join(state.allowed_tools)}\n\n"
        "Choose the next tool call, or stop if the evidence is already sufficient."
    )
