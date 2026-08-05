"""Tool framework contracts (plan § 13, § 14.2).

Tools are read-only, strongly typed, and independently testable. The LLM never
generates SQL or computes metrics; it only consumes ToolResult summaries and
EvidenceDrafts produced here.
"""

import hashlib
import json
import time
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.analytics.base import ALLOWED_DIMENSIONS
from app.harness.artifact_store import ArtifactRef
from app.ontology.registry import EvidenceType

# --- ToolResult (§ 13) ----------------------------------------------------------


class EvidenceDraft(BaseModel):
    """A piece of system evidence produced by a tool (never by the model).

    The EvidenceLedger assigns the final ``evidence_code``; tools only propose
    type/summary/metrics.
    """

    evidence_type: EvidenceType
    summary: str
    metrics: dict[str, float | int | str] = Field(default_factory=dict)
    # Optional dimension context, e.g. {"payment_channel": "channel_b"}.
    dimensions: dict[str, str] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_call_id: str
    tool_name: str
    status: Literal["success", "partial", "failed"]
    summary: str
    evidence: list[EvidenceDraft] = Field(default_factory=list)
    artifact_ref: ArtifactRef | None = None
    row_count: int = 0
    duration_ms: int = 0
    warnings: list[str] = Field(default_factory=list)


# --- Tool protocol ----------------------------------------------------------------


@runtime_checkable
class DiagnosisTool(Protocol):
    name: str
    version: str
    read_only: bool

    def run(self, tool_call_id: str, **kwargs: Any) -> ToolResult: ...


# --- ToolPolicy (§ 14.2) ----------------------------------------------------------

MAX_TOOL_CALLS = 8
TOOL_TIMEOUT_SECONDS = 15
MAX_RESULT_ROWS = 10_000


class ToolPolicyViolation(Exception):
    """Raised when a tool call breaches the policy."""


class ToolPolicy:
    """Enforces call budget, dimension whitelist, dedup, and read-only access."""

    def __init__(
        self,
        max_calls: int = MAX_TOOL_CALLS,
        allowed_dimensions: tuple[str, ...] = ALLOWED_DIMENSIONS,
    ) -> None:
        self._max_calls = max_calls
        self._allowed_dimensions = frozenset(allowed_dimensions)
        self._call_count = 0
        self._seen_fingerprints: set[str] = set()

    @property
    def call_count(self) -> int:
        return self._call_count

    def check_dimension(self, dimension: str) -> None:
        if dimension not in self._allowed_dimensions:
            msg = f"dimension not in whitelist: {dimension!r}"
            raise ToolPolicyViolation(msg)

    def _fingerprint(self, tool_name: str, kwargs: dict[str, Any]) -> str:
        payload = json.dumps({"tool": tool_name, "kwargs": kwargs}, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    def before_call(self, tool: DiagnosisTool, kwargs: dict[str, Any]) -> None:
        if not getattr(tool, "read_only", False):
            msg = f"tool is not read-only: {tool.name}"
            raise ToolPolicyViolation(msg)
        if self._call_count >= self._max_calls:
            msg = f"tool call budget exhausted ({self._max_calls})"
            raise ToolPolicyViolation(msg)
        fp = self._fingerprint(tool.name, kwargs)
        if fp in self._seen_fingerprints:
            msg = f"duplicate tool call: {tool.name}"
            raise ToolPolicyViolation(msg)
        self._seen_fingerprints.add(fp)
        self._call_count += 1


# --- ToolRegistry (§ 14.2) --------------------------------------------------------


class ToolRegistry:
    """Registers tool name/version/schema and enforces read-only registration."""

    def __init__(self) -> None:
        self._tools: dict[str, DiagnosisTool] = {}

    def register(self, tool: DiagnosisTool) -> None:
        if not getattr(tool, "read_only", False):
            msg = f"refusing to register non-read-only tool: {tool.name}"
            raise ToolPolicyViolation(msg)
        self._tools[tool.name] = tool

    def get(self, name: str) -> DiagnosisTool:
        try:
            return self._tools[name]
        except KeyError:
            msg = f"unregistered tool: {name!r}"
            raise ToolPolicyViolation(msg) from None

    def names(self) -> list[str]:
        return sorted(self._tools)

    def execute(
        self, tool_call_id: str, name: str, policy: ToolPolicy, **kwargs: Any
    ) -> ToolResult:
        tool = self.get(name)
        policy.before_call(tool, kwargs)
        start = time.perf_counter()
        result = tool.run(tool_call_id=tool_call_id, **kwargs)
        result.duration_ms = int((time.perf_counter() - start) * 1000)
        return result


# --- EvidenceLedger (§ 14.2) ------------------------------------------------------


class Evidence(BaseModel):
    """A ledger-registered piece of system evidence with a unique code."""

    evidence_code: str
    evidence_type: EvidenceType
    summary: str
    metrics: dict[str, float | int | str]
    dimensions: dict[str, str]
    tool_name: str
    tool_call_id: str

    model_config = {"frozen": True}


class EvidenceLedger:
    """Assigns unique evidence_code to system Evidence. Model never creates these."""

    def __init__(self, prefix: str = "") -> None:
        self._items: list[Evidence] = []
        self._counter = 0
        self._prefix = prefix.strip("-")[:16]

    def record(self, draft: EvidenceDraft, tool_name: str, tool_call_id: str) -> Evidence:
        self._counter += 1
        ev = Evidence(
            evidence_code=(
                f"EV-{self._prefix}-{self._counter:03d}"
                if self._prefix
                else f"EV-{self._counter:03d}"
            ),
            evidence_type=draft.evidence_type,
            summary=draft.summary,
            metrics=draft.metrics,
            dimensions=draft.dimensions,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
        )
        self._items.append(ev)
        return ev

    def record_result(self, result: ToolResult) -> list[Evidence]:
        return [self.record(d, result.tool_name, result.tool_call_id) for d in result.evidence]

    def all(self) -> list[Evidence]:
        return list(self._items)

    def summaries(self) -> list[str]:
        """Context-builder view: codes + one-line summaries, not full detail."""
        return [f"{e.evidence_code} [{e.evidence_type.value}] {e.summary}" for e in self._items]
