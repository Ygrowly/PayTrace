"""Capability routing — a bounded tool set per incident (notes § 8.6).

Handing every tool to the model at once makes "the agent chose this tool" a
weak claim and burns budget on irrelevant queries. Instead the harness derives
a restricted bundle from the incident's initial signals and the Before-Tool
hook refuses anything outside it.

Routing runs once, at incident scoping, so the bundle is a fixed constraint for
the whole investigation rather than something the loop can widen when it is
stuck.
"""

from dataclasses import dataclass
from typing import Literal

from app.domain.events import FunnelStage

Signal = Literal[
    "DATA_INTEGRITY",
    "AUTH_FAILURE",
    "CHANNEL_TIMEOUT",
    "CALLBACK_ANOMALY",
    "DECISION_FRICTION",
    "UNKNOWN",
]

# Tool names as registered in ToolRegistry.
_FUNNEL = "get_payment_funnel"
_BREAKDOWN = "breakdown_conversion_loss"
_BENEFIT = "analyze_benefit_gap"
_CANCEL = "trace_cancel_and_reorder"
_EVENTS = "inspect_payment_events"
_CONFIG = "get_config_changes"

ALL_TOOLS: tuple[str, ...] = (_FUNNEL, _BREAKDOWN, _BENEFIT, _CANCEL, _EVENTS, _CONFIG)

# Priority capabilities per initial signal (notes § 8.6). The first entry is
# where the investigation should start; the rest remain available.
_CAPABILITIES_BY_SIGNAL: dict[str, tuple[str, ...]] = {
    "DATA_INTEGRITY": (_FUNNEL, _EVENTS, _BREAKDOWN),
    "AUTH_FAILURE": (_EVENTS, _BREAKDOWN, _FUNNEL),
    "CHANNEL_TIMEOUT": (_EVENTS, _BREAKDOWN, _FUNNEL, _CONFIG),
    "CALLBACK_ANOMALY": (_EVENTS, _CANCEL, _FUNNEL),
    "DECISION_FRICTION": (_BENEFIT, _CANCEL, _BREAKDOWN, _FUNNEL),
    "UNKNOWN": ALL_TOOLS,
}

_STAGE_SIGNALS: tuple[tuple[frozenset[FunnelStage], str], ...] = (
    (
        frozenset({FunnelStage.AUTHENTICATION_PASSED}),
        "AUTH_FAILURE",
    ),
    (
        frozenset({FunnelStage.PLATFORM_CONFIRMED}),
        "CALLBACK_ANOMALY",
    ),
    (
        frozenset(
            {
                FunnelStage.PAYMENT_METHOD_SELECTED,
                FunnelStage.PAYMENT_INITIATED,
                FunnelStage.PAYMENT_OPTIONS_SHOWN,
            }
        ),
        "DECISION_FRICTION",
    ),
    (
        frozenset({FunnelStage.CHANNEL_SUCCEEDED}),
        "CHANNEL_TIMEOUT",
    ),
)


@dataclass(frozen=True)
class CapabilityBundle:
    """The tool set an investigation is permitted to use, plus why."""

    signals: tuple[str, ...]
    allowed_tools: frozenset[str]
    preferred_first: tuple[str, ...]
    rationale: str

    def allows(self, tool_name: str) -> bool:
        return tool_name in self.allowed_tools


def detect_signals(
    *,
    anomalous_stages: list[str] | tuple[str, ...],
    missing_data: list[str] | tuple[str, ...] = (),
) -> list[str]:
    """Derive initial signals from the incident's first triage results.

    Returns ``["UNKNOWN"]`` when nothing in particular points anywhere — that
    is a real answer, and it widens the bundle rather than guessing.
    """
    signals: list[str] = []
    if missing_data:
        signals.append("DATA_INTEGRITY")

    stages = set()
    for raw in anomalous_stages:
        try:
            stages.add(FunnelStage(raw))
        except ValueError:
            # Unknown stage names still count as "something degraded".
            continue

    for stage_set, signal in _STAGE_SIGNALS:
        if stages & stage_set and signal not in signals:
            signals.append(signal)

    return signals or ["UNKNOWN"]


def route_capabilities(
    *,
    anomalous_stages: list[str] | tuple[str, ...] = (),
    missing_data: list[str] | tuple[str, ...] = (),
    signals: list[str] | None = None,
) -> CapabilityBundle:
    """Build the restricted tool bundle for an incident.

    Signals are unioned: an incident may legitimately show both friction and a
    channel fault, as the default mixed-failure scenario does.
    """
    resolved = (
        list(signals)
        if signals is not None
        else detect_signals(anomalous_stages=anomalous_stages, missing_data=missing_data)
    )

    allowed: list[str] = []
    preferred: list[str] = []
    for signal in resolved:
        for tool in _CAPABILITIES_BY_SIGNAL.get(signal, ()):
            if tool not in allowed:
                allowed.append(tool)
            if tool not in preferred:
                preferred.append(tool)

    # The funnel tool scopes every incident and is always available.
    if _FUNNEL not in allowed:
        allowed.insert(0, _FUNNEL)
        preferred.insert(0, _FUNNEL)

    rationale = f"signals={','.join(resolved)}; " f"{len(allowed)}/{len(ALL_TOOLS)} tools allowed"
    return CapabilityBundle(
        signals=tuple(resolved),
        allowed_tools=frozenset(allowed),
        preferred_first=tuple(preferred),
        rationale=rationale,
    )
