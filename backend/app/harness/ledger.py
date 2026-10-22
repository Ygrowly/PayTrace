"""Hypothesis Ledger — the investigation's working memory (notes § 8.5).

Diagnosis is not a single pass over a report; it is a sequence of hypotheses
that get proposed, tested against tool-produced evidence, and either supported
or rejected. The ledger holds that state so a multi-step investigation can
resume, be replayed, and — critically — refuse to re-investigate an explanation
its own evidence already ruled out.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.ontology.registry import EvidenceType

HypothesisStatus = Literal[
    "PROPOSED",  # raised, not yet tested
    "INVESTIGATING",  # a tool call is currently gathering evidence for it
    "SUPPORTED",  # evidence consistent with the hypothesis
    "PARTIAL",  # some evidence, but alternatives remain open
    "REJECTED",  # evidence contradicts it
    "NEEDS_DATA",  # cannot be settled without data we do not have
]

_TERMINAL_STATUSES: frozenset[str] = frozenset({"SUPPORTED", "PARTIAL", "REJECTED", "NEEDS_DATA"})


class HypothesisTerminal(Exception):
    """Raised when a terminal hypothesis is asked to change state again."""


# Root causes that have a dedicated evidence type. Nothing else may be *ruled
# out* by an empty probe: without a confirming signal to look for, an empty
# result means "we cannot tell", not "it did not happen".
_CONFIRMING_EVIDENCE: frozenset[str] = frozenset(
    {"CHANNEL_TIMEOUT", "BENEFIT_SELECTION_FRICTION", "DATA_QUALITY_ISSUE"}
)


# Which tool actually probes for a root cause. A hypothesis may only be ruled
# out by a call that would have found the evidence — a generic drilldown coming
# back empty proves nothing.
_PROBE_TOOLS: dict[str, frozenset[str]] = {
    "inspect_payment_events": frozenset(
        {"CHANNEL_TIMEOUT", "AUTHENTICATION_FAILURE", "CALLBACK_FAILURE"}
    ),
    "analyze_benefit_gap": frozenset({"BENEFIT_SELECTION_FRICTION"}),
    "get_payment_funnel": frozenset({"DATA_QUALITY_ISSUE"}),
}


def is_designated_probe(tool_name: str, root_cause_type: str) -> bool:
    """Whether ``tool_name`` is the tool that would find evidence for this cause."""
    return root_cause_type in _PROBE_TOOLS.get(tool_name, frozenset())


def evaluate_hypothesis(
    root_cause_type: str,
    evidence_types: set[EvidenceType],
    *,
    probe_completed: bool,
) -> tuple[HypothesisStatus, str | None] | None:
    """Decide what the evidence so far says about one hypothesis.

    Returns ``None`` when the question is still open — no confirming evidence
    has arrived and the probing tool has not run yet.

    Positive verdicts come from :func:`app.diagnosis.validator.classify_support`
    so a hypothesis and the report claim built from the same evidence can never
    disagree about how well supported it is.
    """
    # Imported here rather than at module scope: the harness consumes the
    # evidence contract; the contract does not depend on the harness.
    from app.diagnosis.validator import classify_support

    status, reason = classify_support(root_cause_type, evidence_types)
    if status != "UNKNOWN":
        return status, None

    if not probe_completed:
        return None

    if root_cause_type in _CONFIRMING_EVIDENCE:
        return "REJECTED", reason
    # No evidence type exists that could ever confirm this cause, so an empty
    # probe settles nothing. Saying REJECTED here would overstate what we know.
    return "NEEDS_DATA", f"no evidence type exists yet for {root_cause_type}"


class Hypothesis(BaseModel):
    """One root-cause candidate and the evidence gathered for and against it."""

    hypothesis_id: str
    root_cause_type: str
    proposed_scope: dict[str, Any] = Field(default_factory=dict)
    supporting_evidence: list[str] = Field(default_factory=list)
    conflicting_evidence: list[str] = Field(default_factory=list)
    alternative_explanations: list[str] = Field(default_factory=list)
    required_next_tool: str | None = None
    status: HypothesisStatus = "PROPOSED"
    estimated_loss_range: tuple[int, int] | None = None
    rejection_reason: str | None = None

    model_config = {"frozen": True}


class HypothesisLedger:
    """Mutable collection of hypotheses for one diagnosis run.

    ``propose`` de-duplicates by root cause type: raising the same explanation
    twice without new evidence is exactly the loop the ledger exists to stop.
    """

    def __init__(self) -> None:
        self._items: list[Hypothesis] = []
        self._counter = 0
        self._rejected_types: dict[str, str] = {}

    # -- proposal ------------------------------------------------------------

    def propose(
        self,
        root_cause_type: str,
        *,
        required_next_tool: str | None = None,
        proposed_scope: dict[str, Any] | None = None,
        alternative_explanations: list[str] | None = None,
    ) -> Hypothesis:
        """Raise a new hypothesis, or return the existing one for this type.

        Re-proposing a REJECTED explanation raises unless a caller passes a
        genuinely new tool, which is how the harness distinguishes "test it
        differently" from "ask the same question again".
        """
        existing = self._find(root_cause_type)
        if existing is not None:
            if existing.status == "REJECTED" and required_next_tool == existing.required_next_tool:
                raise HypothesisTerminal(
                    f"{root_cause_type} was rejected; re-proposing it requires a new tool"
                )
            return existing

        self._counter += 1
        hypothesis = Hypothesis(
            hypothesis_id=f"H-{self._counter:02d}",
            root_cause_type=root_cause_type,
            proposed_scope=proposed_scope or {},
            required_next_tool=required_next_tool,
            alternative_explanations=alternative_explanations or [],
        )
        self._items.append(hypothesis)
        return hypothesis

    # -- transitions ---------------------------------------------------------

    def start(self, hypothesis_id: str) -> Hypothesis:
        """Mark a hypothesis as under investigation."""
        current = self._require(hypothesis_id)
        if current.status in _TERMINAL_STATUSES:
            raise HypothesisTerminal(f"{hypothesis_id} is already {current.status}")
        return self._replace(hypothesis_id, status="INVESTIGATING")

    def record_evidence(
        self, hypothesis_id: str, evidence_code: str, *, supports: bool
    ) -> Hypothesis:
        """Attach an evidence code for or against a hypothesis."""
        current = self._require(hypothesis_id)
        if supports:
            updated = current.supporting_evidence + [evidence_code]
            return self._replace(hypothesis_id, supporting_evidence=updated)
        updated = current.conflicting_evidence + [evidence_code]
        return self._replace(hypothesis_id, conflicting_evidence=updated)

    def resolve(
        self,
        hypothesis_id: str,
        status: HypothesisStatus,
        *,
        reason: str | None = None,
        estimated_loss_range: tuple[int, int] | None = None,
    ) -> Hypothesis:
        """Move a hypothesis to a terminal state."""
        if status not in _TERMINAL_STATUSES:
            raise ValueError(f"{status!r} is not a terminal hypothesis status")
        self._require(hypothesis_id)
        resolved = self._replace(
            hypothesis_id,
            status=status,
            rejection_reason=reason,
            estimated_loss_range=estimated_loss_range,
        )
        if status == "REJECTED":
            self._rejected_types[resolved.root_cause_type] = reason or "rejected by evidence"
        return resolved

    # -- queries -------------------------------------------------------------

    def all(self) -> list[Hypothesis]:
        return list(self._items)

    def get(self, hypothesis_id: str) -> Hypothesis | None:
        return next((h for h in self._items if h.hypothesis_id == hypothesis_id), None)

    def open_hypotheses(self) -> list[Hypothesis]:
        return [h for h in self._items if h.status not in _TERMINAL_STATUSES]

    def rejected_types(self) -> dict[str, str]:
        return dict(self._rejected_types)

    def is_rejected(self, root_cause_type: str) -> bool:
        return root_cause_type in self._rejected_types

    # -- internals -----------------------------------------------------------

    def _find(self, root_cause_type: str) -> Hypothesis | None:
        return next((h for h in self._items if h.root_cause_type == root_cause_type), None)

    def _require(self, hypothesis_id: str) -> Hypothesis:
        found = self.get(hypothesis_id)
        if found is None:
            raise KeyError(f"unknown hypothesis: {hypothesis_id!r}")
        return found

    def _replace(self, hypothesis_id: str, **updates: Any) -> Hypothesis:
        updated = self._require(hypothesis_id).model_copy(update=updates)
        self._items = [updated if h.hypothesis_id == hypothesis_id else h for h in self._items]
        return updated
