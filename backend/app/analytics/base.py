"""PaymentAnalyticsSource protocol and query/result models (plan § 9).

The business layer (tools) depends only on this protocol. The DuckDB
implementation must not leak its connection, must parameterise all SQL, use a
dimension whitelist, and cap result rows.
"""

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.domain.events import FunnelStage

# --- Dimension whitelist (plan § 13.2) ---------------------------------------

ALLOWED_DIMENSIONS: tuple[str, ...] = (
    "payment_method",
    "payment_channel",
    "region",
    "currency",
    "client_version",
)

PeriodLiteral = Literal["baseline", "incident"]


# --- Funnel (§ 13.1) ----------------------------------------------------------


class FunnelQuery(BaseModel):
    dataset_ref: str
    # Optional dimension filter, e.g. {"payment_channel": "channel_b"}.
    filters: dict[str, str] = Field(default_factory=dict)


class FunnelStageStat(BaseModel):
    stage: str
    reached_count: int
    # Conversion from the previous stage (None for the first stage).
    step_rate: float | None
    # Conversion relative to ORDER_CONFIRMED.
    overall_rate: float


class FunnelPeriodStats(BaseModel):
    period: PeriodLiteral
    stages: list[FunnelStageStat]
    order_confirmed_count: int
    completed_count: int


class FunnelStageDelta(BaseModel):
    stage: str
    baseline_overall_rate: float
    incident_overall_rate: float
    rate_delta: float  # incident - baseline
    # Observational estimate of lost intents vs baseline reach.
    estimated_lost_intents: int


class FunnelResult(BaseModel):
    baseline: FunnelPeriodStats
    incident: FunnelPeriodStats
    deltas: list[FunnelStageDelta]
    # Stages whose |rate_delta| exceeds the tool's anomaly threshold.
    anomalous_stages: list[str]


# --- Breakdown (§ 13.2) -------------------------------------------------------


class BreakdownQuery(BaseModel):
    dataset_ref: str
    dimension: str  # must be in ALLOWED_DIMENSIONS
    top_k: int = Field(default=10, le=20)


class BreakdownRow(BaseModel):
    dimension_value: str
    baseline_order_confirmed: int
    incident_order_confirmed: int
    baseline_completed: int
    incident_completed: int
    baseline_rate: float
    incident_rate: float
    rate_delta: float
    estimated_lost_intents: int


class BreakdownResult(BaseModel):
    dimension: str
    rows: list[BreakdownRow]


# --- Benefit gap (§ 13.3) -----------------------------------------------------


class BenefitQuery(BaseModel):
    dataset_ref: str


class BenefitGapBucket(BaseModel):
    # e.g. "0-300", "300-1000", ">=1000"
    bucket: str
    intent_count: int
    cancel_rate: float
    reorder_rate: float
    switch_method_rate: float
    reorder_recovery_rate: float


class BenefitPeriodStats(BaseModel):
    period: PeriodLiteral
    buckets: list[BenefitGapBucket]
    mean_gap_minor: float


class BenefitResult(BaseModel):
    baseline: BenefitPeriodStats
    incident: BenefitPeriodStats
    # incident mean gap - baseline mean gap
    mean_gap_shift_minor: float


# --- Payment event inspection (§ 13.4) ----------------------------------------


class PaymentEventQuery(BaseModel):
    dataset_ref: str
    top_k: int = Field(default=10, le=20)


class ErrorCodeCount(BaseModel):
    error_code: str
    count: int


class LatencyStats(BaseModel):
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None


class PaymentEventPeriodStats(BaseModel):
    period: PeriodLiteral
    status_counts: dict[str, int]
    top_error_codes: list[ErrorCodeCount]
    latency: LatencyStats
    affected_payment_methods: list[str]
    affected_payment_channels: list[str]


class PaymentEventResult(BaseModel):
    baseline: PaymentEventPeriodStats
    incident: PaymentEventPeriodStats


# --- Dataset validation (§ 9 / data quality) -----------------------------------


class DatasetValidationResult(BaseModel):
    dataset_ref: str
    ok: bool
    row_count: int
    duplicate_event_ids: int
    null_rates: dict[str, float]
    # Stages present in data vs expected funnel stages.
    missing_stages: list[str]
    warnings: list[str]


# --- Protocol -------------------------------------------------------------------


@runtime_checkable
class PaymentAnalyticsSource(Protocol):
    def get_funnel(self, query: FunnelQuery) -> FunnelResult: ...
    def breakdown_loss(self, query: BreakdownQuery) -> BreakdownResult: ...
    def analyze_benefit_gap(self, query: BenefitQuery) -> BenefitResult: ...
    def inspect_payment_events(self, query: PaymentEventQuery) -> PaymentEventResult: ...
    def validate_dataset(self, dataset_ref: str) -> DatasetValidationResult: ...


__all__ = [
    "ALLOWED_DIMENSIONS",
    "FunnelStage",
    "PaymentAnalyticsSource",
]
