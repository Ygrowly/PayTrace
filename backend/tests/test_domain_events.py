"""Unit tests for the Canonical Payment Event model."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.events import (
    CANONICAL_EVENT_COLUMNS,
    FUNNEL_STAGE_ORDER,
    CanonicalPaymentEvent,
    EventStatus,
    EventType,
    FunnelStage,
    Period,
)


def _make_event(**overrides) -> CanonicalPaymentEvent:
    base = {
        "event_id": "evt-1",
        "event_time": datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC),
        "source_system": "simulator",
        "source_event_type": "funnel_progression",
        "scenario_id": "normal",
        "period": Period.BASELINE,
        "purchase_intent_id": "pi-1",
        "order_id": "ord-1",
        "user_id_hash": "u_hash_1",
        "event_type": EventType.FUNNEL_PROGRESSION,
        "funnel_stage": FunnelStage.ORDER_CONFIRMED,
        "status": EventStatus.SUCCESS,
        "region": "CN",
        "currency": "CNY",
        "client_version": "1.0.0",
        "order_amount_minor": 10000,
    }
    base.update(overrides)
    return CanonicalPaymentEvent(**base)


def test_happy_path_minimal_fields():
    evt = _make_event()
    assert evt.schema_version == "paytrace.event.v1"
    assert evt.mapping_version == "paytrace.mapping.v1"
    assert evt.funnel_stage == FunnelStage.ORDER_CONFIRMED


def test_frozen_model_rejects_mutation():
    evt = _make_event()
    with pytest.raises(ValidationError):
        evt.status = EventStatus.FAILED  # type: ignore[misc]


def test_negative_amount_rejected():
    with pytest.raises(ValidationError):
        _make_event(order_amount_minor=-1)


def test_negative_latency_rejected():
    with pytest.raises(ValidationError):
        _make_event(latency_ms=-5)


def test_funnel_stage_order_has_nine_stages():
    assert len(FUNNEL_STAGE_ORDER) == 9
    assert FUNNEL_STAGE_ORDER[0] == FunnelStage.ORDER_CONFIRMED
    assert FUNNEL_STAGE_ORDER[-1] == FunnelStage.PAYMENT_COMPLETED


def test_column_list_matches_model_fields():
    assert CANONICAL_EVENT_COLUMNS[0] == "schema_version"
    assert "event_id" in CANONICAL_EVENT_COLUMNS
    assert "latency_ms" in CANONICAL_EVENT_COLUMNS
    # 27 fields per plan § 8 table.
    assert len(CANONICAL_EVENT_COLUMNS) == 27
