"""Deterministic scenario generator (plan § 12).

Generates Canonical Payment Events for five scenario kinds. A fixed random
seed per (scenario_kind, seed) pair makes generation byte-for-byte
reproducible. Each scenario contains a baseline and an incident period with
comparable order-confirmed volume. One PurchaseIntent may link cancellation,
re-order and eventual recovery.

Ground Truth is produced separately (ground_truth.py) and never mixed into
the runtime event dataset.
"""

import hashlib
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.domain.events import (
    FUNNEL_STAGE_ORDER,
    CanonicalPaymentEvent,
    EventStatus,
    EventType,
    FunnelStage,
    Period,
)
from app.harness.scenarios.ground_truth import (
    GroundTruth,
    InjectedParameters,
    ScenarioKind,
)

# --- Dimension value pools (deterministic, no real-user data) ----------------

_PAYMENT_METHODS = ["card", "wallet", "bank_transfer"]
_PAYMENT_CHANNELS = ["channel_a", "channel_b", "channel_c"]
_REGIONS = ["CN", "US", "EU"]
_CURRENCIES = ["CNY", "USD", "EUR"]
_CLIENT_VERSIONS = ["1.0.0", "1.1.0", "1.2.0"]

# Baseline per-stage conditional reach probabilities (index-aligned with
# FUNNEL_STAGE_ORDER; stage 0 is always reached by definition).
_BASELINE_REACH = {
    FunnelStage.ORDER_CONFIRMED: 1.0,
    FunnelStage.CHECKOUT_ENTERED: 0.92,
    FunnelStage.PAYMENT_OPTIONS_SHOWN: 0.98,
    FunnelStage.PAYMENT_METHOD_SELECTED: 0.95,
    FunnelStage.PAYMENT_INITIATED: 0.97,
    FunnelStage.AUTHENTICATION_PASSED: 0.96,
    FunnelStage.CHANNEL_SUCCEEDED: 0.97,
    FunnelStage.PLATFORM_CONFIRMED: 0.99,
    FunnelStage.PAYMENT_COMPLETED: 0.995,
}

_BASELINE_TIMEOUT_RATE = 0.01
_BASELINE_LATENCY_MS = (120, 800)  # uniform range


@dataclass(frozen=True)
class ScenarioConfig:
    kind: ScenarioKind
    seed: int
    num_intents: int = 5000
    baseline_days: int = 7
    incident_days: int = 7
    start_time: datetime = datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC)


@dataclass
class _IntentState:
    """Mutable per-intent generation state."""

    purchase_intent_id: str
    order_id: str
    user_id_hash: str
    region: str
    currency: str
    client_version: str
    payment_method: str
    payment_channel: str
    order_amount_minor: int
    best_payable_minor: int
    selected_payable_minor: int
    benefit_id: str | None
    base_time: datetime
    period: Period
    cancelled: bool = False
    reordered: bool = False
    switched_method: bool = False
    timed_out: bool = False
    reached_stage: FunnelStage = FunnelStage.ORDER_CONFIRMED
    latency_ms: int | None = None
    error_code: str | None = None


def _stable_seed(kind: str, seed: int, period: Period) -> int:
    """Derive a deterministic per-period seed."""
    digest = hashlib.sha256(f"{kind}:{seed}:{period}".encode()).hexdigest()
    return int(digest[:16], 16)


def _make_event(state: _IntentState, stage: FunnelStage, seq: int, **kw) -> CanonicalPaymentEvent:
    offset = timedelta(minutes=seq * 2, seconds=state.base_time.second)
    return CanonicalPaymentEvent(
        event_id=f"{state.purchase_intent_id}-{stage.value}",
        event_time=state.base_time + offset,
        source_system="simulator",
        source_event_type="funnel_progression",
        scenario_id="",  # filled by caller
        period=state.period,
        purchase_intent_id=state.purchase_intent_id,
        order_id=state.order_id,
        checkout_session_id=f"cs-{state.order_id}",
        payment_attempt_id=f"pa-{state.order_id}",
        user_id_hash=state.user_id_hash,
        event_type=EventType.FUNNEL_PROGRESSION,
        funnel_stage=stage,
        status=EventStatus.SUCCESS,
        payment_method=state.payment_method,
        payment_channel=state.payment_channel,
        region=state.region,
        currency=state.currency,
        client_version=state.client_version,
        order_amount_minor=state.order_amount_minor,
        selected_payable_minor=state.selected_payable_minor,
        best_payable_minor=state.best_payable_minor,
        benefit_id=state.benefit_id,
        latency_ms=kw.get("latency_ms"),
        error_code=kw.get("error_code"),
    )


def _gen_intent_base(
    rng: random.Random, idx: int, period: Period, cfg: ScenarioConfig
) -> _IntentState:
    order_amount = rng.choice([5000, 8000, 10000, 15000, 20000, 30000])
    # Baseline benefit gap: small (0-300 minor units).
    gap = rng.randint(0, 300)
    best_payable = order_amount - rng.randint(0, 500)
    selected_payable = best_payable + gap
    benefit_id = f"bnf-{rng.randint(1, 50)}" if rng.random() < 0.7 else None

    day_offset = rng.randint(
        0, (cfg.baseline_days if period == Period.BASELINE else cfg.incident_days) - 1
    )
    if period == Period.INCIDENT:
        day_offset += cfg.baseline_days
    base_time = cfg.start_time + timedelta(
        days=day_offset,
        hours=rng.randint(0, 23),
        minutes=rng.randint(0, 59),
        seconds=rng.randint(0, 59),
    )

    return _IntentState(
        purchase_intent_id=f"pi-{period.value[:3]}-{idx:06d}",
        order_id=f"ord-{period.value[:3]}-{idx:06d}",
        user_id_hash=hashlib.sha256(f"user-{idx}-{period.value}".encode()).hexdigest()[:16],
        region=rng.choice(_REGIONS),
        currency=rng.choice(_CURRENCIES),
        client_version=rng.choice(_CLIENT_VERSIONS),
        payment_method=rng.choice(_PAYMENT_METHODS),
        payment_channel=rng.choice(_PAYMENT_CHANNELS),
        order_amount_minor=order_amount,
        best_payable_minor=best_payable,
        selected_payable_minor=selected_payable,
        benefit_id=benefit_id,
        base_time=base_time,
        period=period,
    )


def _apply_benefit_friction(
    rng: random.Random, state: _IntentState, params: InjectedParameters
) -> None:
    """Shift benefit gap up; high-gap intents cancel / switch / reorder more."""
    state.selected_payable_minor += params.benefit_gap_shift_minor
    gap = state.selected_payable_minor - state.best_payable_minor
    if gap >= 1000:  # high-gap bucket
        r = rng.random()
        if r < params.high_gap_cancel_rate:
            state.cancelled = True
            if rng.random() < 0.6:
                state.reordered = True
        elif r < params.high_gap_cancel_rate + params.high_gap_switch_rate:
            state.switched_method = True
            state.payment_method = rng.choice(
                [m for m in _PAYMENT_METHODS if m != state.payment_method]
            )


def _apply_channel_timeout(
    rng: random.Random, state: _IntentState, params: InjectedParameters
) -> None:
    if state.payment_channel != params.timeout_channel:
        return
    if rng.random() < params.timeout_rate:
        state.timed_out = True
        state.error_code = "CHANNEL_TIMEOUT"
        state.latency_ms = int(
            rng.uniform(*_BASELINE_LATENCY_MS) * params.timeout_latency_multiplier
        )


def _walk_funnel(rng: random.Random, state: _IntentState, reach: dict[FunnelStage, float]) -> None:
    """Advance the intent through the funnel until it drops out or completes."""
    for stage in FUNNEL_STAGE_ORDER[1:]:
        if rng.random() >= reach[stage]:
            break
        state.reached_stage = stage
    if state.timed_out and FUNNEL_STAGE_ORDER.index(
        state.reached_stage
    ) >= FUNNEL_STAGE_ORDER.index(FunnelStage.CHANNEL_SUCCEEDED):
        # A timed-out intent cannot pass channel stage.
        state.reached_stage = FunnelStage.AUTHENTICATION_PASSED


def _emit_events(
    state: _IntentState, scenario_id: str, drop_stages: set[str]
) -> list[CanonicalPaymentEvent]:
    events: list[CanonicalPaymentEvent] = []
    reached_idx = FUNNEL_STAGE_ORDER.index(state.reached_stage)
    for seq, stage in enumerate(FUNNEL_STAGE_ORDER[: reached_idx + 1]):
        if stage.value in drop_stages:
            continue
        ev = _make_event(
            state, stage, seq, latency_ms=state.latency_ms, error_code=state.error_code
        )
        events.append(ev.model_copy(update={"scenario_id": scenario_id}))

    # Branch events (cancel / reorder / switch / timeout failure).
    branch_seq = len(events)
    if state.cancelled:
        ev = _make_event(state, state.reached_stage, branch_seq).model_copy(
            update={
                "scenario_id": scenario_id,
                "event_id": f"{state.purchase_intent_id}-ORDER_CANCELLED",
                "event_type": EventType.ORDER_CANCELLED,
                "status": EventStatus.CANCELLED,
                "funnel_stage": None,
            }
        )
        events.append(ev)
        branch_seq += 1
    if state.reordered:
        ev = _make_event(state, state.reached_stage, branch_seq).model_copy(
            update={
                "scenario_id": scenario_id,
                "event_id": f"{state.purchase_intent_id}-REORDERED",
                "event_type": EventType.REORDERED,
                "funnel_stage": None,
            }
        )
        events.append(ev)
        branch_seq += 1
    if state.switched_method:
        ev = _make_event(state, state.reached_stage, branch_seq).model_copy(
            update={
                "scenario_id": scenario_id,
                "event_id": f"{state.purchase_intent_id}-METHOD_SWITCHED",
                "event_type": EventType.PAYMENT_METHOD_SWITCHED,
                "funnel_stage": None,
            }
        )
        events.append(ev)
        branch_seq += 1
    if state.timed_out:
        ev = _make_event(state, state.reached_stage, branch_seq).model_copy(
            update={
                "scenario_id": scenario_id,
                "event_id": f"{state.purchase_intent_id}-PAYMENT_TIMEOUT",
                "event_type": EventType.PAYMENT_TIMEOUT,
                "status": EventStatus.TIMEOUT,
                "funnel_stage": None,
                "error_code": "CHANNEL_TIMEOUT",
                "latency_ms": state.latency_ms,
            }
        )
        events.append(ev)
    return events


def _params_for(kind: ScenarioKind, period: Period) -> InjectedParameters:
    """Fault-injection parameters. Baseline period is always clean."""
    if period == Period.BASELINE:
        return InjectedParameters()
    if kind == "benefit_friction":
        return InjectedParameters(
            benefit_gap_shift_minor=1200,
            high_gap_cancel_rate=0.35,
            high_gap_switch_rate=0.25,
        )
    if kind == "channel_timeout":
        return InjectedParameters(
            timeout_channel="channel_b",
            timeout_rate=0.30,
            timeout_latency_multiplier=6.0,
        )
    if kind == "mixed_failure":
        return InjectedParameters(
            benefit_gap_shift_minor=1200,
            high_gap_cancel_rate=0.35,
            high_gap_switch_rate=0.25,
            timeout_channel="channel_b",
            timeout_rate=0.30,
            timeout_latency_multiplier=6.0,
        )
    if kind == "data_gap":
        return InjectedParameters(
            drop_funnel_stages=[
                FunnelStage.AUTHENTICATION_PASSED.value,
                FunnelStage.CHANNEL_SUCCEEDED.value,
            ],
            null_benefit_id_rate=0.85,
        )
    return InjectedParameters()  # normal


def _ground_truth_for(cfg: ScenarioConfig) -> GroundTruth:
    kind = cfg.kind
    if kind == "benefit_friction":
        return GroundTruth(
            scenario_id=kind,
            expected_anomalous_stages=[FunnelStage.PAYMENT_METHOD_SELECTED.value],
            expected_root_causes=["BENEFIT_FRICTION"],
            affected_dimensions={"payment_method": _PAYMENT_METHODS},
            injected_parameters=_params_for(kind, Period.INCIDENT),
            expected_data_gaps=[],
            random_seed=cfg.seed,
            created_at=cfg.start_time,
        )
    if kind == "channel_timeout":
        return GroundTruth(
            scenario_id=kind,
            expected_anomalous_stages=[FunnelStage.CHANNEL_SUCCEEDED.value],
            expected_root_causes=["CHANNEL_TIMEOUT"],
            affected_dimensions={"payment_channel": ["channel_b"]},
            injected_parameters=_params_for(kind, Period.INCIDENT),
            expected_data_gaps=[],
            random_seed=cfg.seed,
            created_at=cfg.start_time,
        )
    if kind == "mixed_failure":
        return GroundTruth(
            scenario_id=kind,
            expected_anomalous_stages=[
                FunnelStage.PAYMENT_METHOD_SELECTED.value,
                FunnelStage.CHANNEL_SUCCEEDED.value,
            ],
            expected_root_causes=["BENEFIT_FRICTION", "CHANNEL_TIMEOUT"],
            affected_dimensions={
                "payment_method": _PAYMENT_METHODS,
                "payment_channel": ["channel_b"],
            },
            injected_parameters=_params_for(kind, Period.INCIDENT),
            expected_data_gaps=[],
            random_seed=cfg.seed,
            created_at=cfg.start_time,
        )
    if kind == "data_gap":
        return GroundTruth(
            scenario_id=kind,
            expected_anomalous_stages=[],
            expected_root_causes=["NEEDS_DATA"],
            affected_dimensions={},
            injected_parameters=_params_for(kind, Period.INCIDENT),
            expected_data_gaps=[
                FunnelStage.AUTHENTICATION_PASSED.value,
                FunnelStage.CHANNEL_SUCCEEDED.value,
                "benefit_id",
            ],
            random_seed=cfg.seed,
            created_at=cfg.start_time,
        )
    return GroundTruth(
        scenario_id=kind,
        expected_anomalous_stages=[],
        expected_root_causes=["NORMAL_FLUCTUATION"],
        affected_dimensions={},
        injected_parameters=InjectedParameters(),
        expected_data_gaps=[],
        random_seed=cfg.seed,
        created_at=cfg.start_time,
    )


def generate_scenario(cfg: ScenarioConfig) -> tuple[list[CanonicalPaymentEvent], GroundTruth]:
    """Generate all events + ground truth for one scenario. Deterministic."""
    events: list[CanonicalPaymentEvent] = []
    for period in (Period.BASELINE, Period.INCIDENT):
        rng = random.Random(_stable_seed(cfg.kind, cfg.seed, period))  # noqa: S311 - deterministic simulation, not crypto
        params = _params_for(cfg.kind, period)
        drop_stages = set(params.drop_funnel_stages)
        for idx in range(cfg.num_intents):
            state = _gen_intent_base(rng, idx, period, cfg)
            if period == Period.INCIDENT:
                if params.benefit_gap_shift_minor:
                    _apply_benefit_friction(rng, state, params)
                if params.timeout_channel:
                    _apply_channel_timeout(rng, state, params)
                if params.null_benefit_id_rate and rng.random() < params.null_benefit_id_rate:
                    state.benefit_id = None
            _walk_funnel(rng, state, _BASELINE_REACH)
            events.extend(_emit_events(state, cfg.kind, drop_stages))
    gt = _ground_truth_for(cfg)
    return events, gt
