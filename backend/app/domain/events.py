"""Canonical Payment Event (plan § 8).

All analytics data sources must map into this single event model. Amounts are
integers in the smallest currency unit (minor); timestamps are UTC. No real
PAN / phone / name / address / account credentials are ever generated or
stored (plan § 8, § 22).
"""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "paytrace.event.v1"
MAPPING_VERSION = "paytrace.mapping.v1"


class FunnelStage(StrEnum):
    """Standard funnel stages (plan § 8.1).

    Cancellation, re-order and payment failure are event branches, not
    primary funnel stages.
    """

    ORDER_CONFIRMED = "ORDER_CONFIRMED"
    CHECKOUT_ENTERED = "CHECKOUT_ENTERED"
    PAYMENT_OPTIONS_SHOWN = "PAYMENT_OPTIONS_SHOWN"
    PAYMENT_METHOD_SELECTED = "PAYMENT_METHOD_SELECTED"
    PAYMENT_INITIATED = "PAYMENT_INITIATED"
    AUTHENTICATION_PASSED = "AUTHENTICATION_PASSED"
    CHANNEL_SUCCEEDED = "CHANNEL_SUCCEEDED"
    PLATFORM_CONFIRMED = "PLATFORM_CONFIRMED"
    PAYMENT_COMPLETED = "PAYMENT_COMPLETED"


# Ordered list for funnel computation (order matters).
FUNNEL_STAGE_ORDER: list[FunnelStage] = [
    FunnelStage.ORDER_CONFIRMED,
    FunnelStage.CHECKOUT_ENTERED,
    FunnelStage.PAYMENT_OPTIONS_SHOWN,
    FunnelStage.PAYMENT_METHOD_SELECTED,
    FunnelStage.PAYMENT_INITIATED,
    FunnelStage.AUTHENTICATION_PASSED,
    FunnelStage.CHANNEL_SUCCEEDED,
    FunnelStage.PLATFORM_CONFIRMED,
    FunnelStage.PAYMENT_COMPLETED,
]


class EventType(StrEnum):
    """Standard event types. Funnel progression events carry a funnel_stage;

    branch events (cancel / reorder / failure) do not.
    """

    FUNNEL_PROGRESSION = "FUNNEL_PROGRESSION"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PAYMENT_TIMEOUT = "PAYMENT_TIMEOUT"
    AUTH_FAILED = "AUTH_FAILED"
    CALLBACK_EXCEPTION = "CALLBACK_EXCEPTION"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    REORDERED = "REORDERED"
    PAYMENT_METHOD_SWITCHED = "PAYMENT_METHOD_SWITCHED"


class EventStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class Period(StrEnum):
    BASELINE = "baseline"
    INCIDENT = "incident"


class CanonicalPaymentEvent(BaseModel):
    """Canonical event row. Field set per plan § 8 table."""

    schema_version: Literal["paytrace.event.v1"] = SCHEMA_VERSION
    event_id: str
    event_time: datetime  # UTC
    source_system: str
    source_event_type: str
    mapping_version: str = MAPPING_VERSION
    scenario_id: str
    period: Period
    purchase_intent_id: str
    order_id: str
    checkout_session_id: str | None = None
    payment_attempt_id: str | None = None
    user_id_hash: str
    event_type: EventType
    funnel_stage: FunnelStage | None = None
    status: EventStatus
    payment_method: str | None = None
    payment_channel: str | None = None
    region: str
    currency: str
    client_version: str
    order_amount_minor: int = Field(ge=0)
    selected_payable_minor: int | None = Field(default=None, ge=0)
    best_payable_minor: int | None = Field(default=None, ge=0)
    benefit_id: str | None = None
    error_code: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)

    model_config = {"frozen": True}


# Column order used when writing Parquet datasets. Kept explicit so the
# generator, validator and DuckDB source agree on a stable schema.
CANONICAL_EVENT_COLUMNS: list[str] = list(CanonicalPaymentEvent.model_fields.keys())
