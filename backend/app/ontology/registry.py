"""Code-first PayTrace Ontology v1 (plan § 7).

The Ontology is the unified semantic layer for payment diagnosis — not a
database. It is defined as Pydantic models plus a Python registry, versioned
as ``paytrace.ontology.v1``. The registry is validated at import time and can
emit JSON Schema for API docs and the frontend.

Layering rules (plan § 7.7):
- Ontology models must NOT reference ``app.db`` (no SQLAlchemy coupling).
- ORM models must NOT inherit from Ontology models.
- Service layer performs ORM <-> Ontology <-> API Schema conversion.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

ONTOLOGY_VERSION = "paytrace.ontology.v1"


# --- Object / Link / Action / Evidence type enums ---------------------------


class ObjectType(StrEnum):
    PURCHASE_INTENT = "PurchaseIntent"
    ORDER = "Order"
    CHECKOUT_SESSION = "CheckoutSession"
    PAYMENT_ATTEMPT = "PaymentAttempt"
    PAYMENT_METHOD = "PaymentMethod"
    BENEFIT = "Benefit"
    PAYMENT_CHANNEL = "PaymentChannel"
    PAYMENT_EVENT = "PaymentEvent"
    INCIDENT = "Incident"
    DIAGNOSIS_RUN = "DiagnosisRun"
    EVIDENCE = "Evidence"
    DIAGNOSIS_REPORT = "DiagnosisReport"
    EVALUATION_RUN = "EvaluationRun"


class LinkType(StrEnum):
    CONTAINS = "contains"  # PurchaseIntent -> Order
    OPENS = "opens"  # Order -> CheckoutSession
    CREATES = "creates"  # Order -> PaymentAttempt
    USES = "uses"  # PaymentAttempt -> PaymentMethod
    ROUTED_TO = "routed_to"  # PaymentAttempt -> PaymentChannel
    AFFECTS = "affects"  # Incident -> PurchaseIntent / PaymentAttempt
    SUPPORTED_BY = "supported_by"  # DiagnosisReport -> Evidence
    EVALUATES = "evaluates"  # EvaluationRun -> DiagnosisRun


class ActionType(StrEnum):
    CREATE_INCIDENT = "CreateIncident"
    RUN_DIAGNOSIS = "RunDiagnosis"
    RETRY_DIAGNOSIS = "RetryDiagnosis"
    REQUEST_DATA = "RequestData"
    ACCEPT_CAUSE = "AcceptCause"
    REJECT_CAUSE = "RejectCause"
    RESOLVE_INCIDENT = "ResolveIncident"


class EvidenceType(StrEnum):
    """Kinds of deterministic evidence a tool may produce."""

    FUNNEL_STAGE_DEGRADATION = "FUNNEL_STAGE_DEGRADATION"
    DIMENSION_CONTRIBUTION = "DIMENSION_CONTRIBUTION"
    BENEFIT_GAP_FRICTION = "BENEFIT_GAP_FRICTION"
    CHANNEL_TIMEOUT = "CHANNEL_TIMEOUT"
    ERROR_CODE_CONCENTRATION = "ERROR_CODE_CONCENTRATION"
    DATA_GAP = "DATA_GAP"


class RootCauseLabel(StrEnum):
    """Root-cause labels the model may choose from (plan § 15.3).

    The model must NOT create arbitrary labels.
    """

    BENEFIT_SELECTION_FRICTION = "BENEFIT_SELECTION_FRICTION"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    CHANNEL_TIMEOUT = "CHANNEL_TIMEOUT"
    CALLBACK_FAILURE = "CALLBACK_FAILURE"
    NORMAL_PAYMENT_FAILURE = "NORMAL_PAYMENT_FAILURE"
    DATA_QUALITY_ISSUE = "DATA_QUALITY_ISSUE"
    UNKNOWN = "UNKNOWN"


# --- Registry entry models ---------------------------------------------------


class ObjectDefinition(BaseModel):
    object_type: ObjectType
    description: str
    ontology_version: Literal["paytrace.ontology.v1"] = ONTOLOGY_VERSION


class LinkDefinition(BaseModel):
    link_type: LinkType
    source: ObjectType
    target: ObjectType
    ontology_version: Literal["paytrace.ontology.v1"] = ONTOLOGY_VERSION


class MetricDefinition(BaseModel):
    name: str
    description: str
    unit: str
    ontology_version: Literal["paytrace.ontology.v1"] = ONTOLOGY_VERSION


class DimensionDefinition(BaseModel):
    name: str
    description: str
    ontology_version: Literal["paytrace.ontology.v1"] = ONTOLOGY_VERSION


class ActionDefinition(BaseModel):
    action_type: ActionType
    description: str
    exposed_to_frontend: bool
    ontology_version: Literal["paytrace.ontology.v1"] = ONTOLOGY_VERSION


class EvidenceTypeDefinition(BaseModel):
    evidence_type: EvidenceType
    description: str
    ontology_version: Literal["paytrace.ontology.v1"] = ONTOLOGY_VERSION


class OntologyRegistry(BaseModel):
    """Immutable v1 registry. Validated at construction; no runtime mutation."""

    version: Literal["paytrace.ontology.v1"] = ONTOLOGY_VERSION
    objects: list[ObjectDefinition]
    links: list[LinkDefinition]
    metrics: list[MetricDefinition]
    dimensions: list[DimensionDefinition]
    actions: list[ActionDefinition]
    evidence_types: list[EvidenceTypeDefinition]

    model_config = {"frozen": True}

    def dimension_names(self) -> set[str]:
        return {d.name for d in self.dimensions}

    def frontend_action_types(self) -> set[ActionType]:
        return {a.action_type for a in self.actions if a.exposed_to_frontend}


# --- V1 registry content -----------------------------------------------------

_OBJECTS: list[ObjectDefinition] = [
    ObjectDefinition(
        object_type=ObjectType.PURCHASE_INTENT, description="User's intent to purchase."
    ),
    ObjectDefinition(object_type=ObjectType.ORDER, description="A confirmed order."),
    ObjectDefinition(
        object_type=ObjectType.CHECKOUT_SESSION, description="Checkout session for an order."
    ),
    ObjectDefinition(
        object_type=ObjectType.PAYMENT_ATTEMPT, description="A single payment attempt."
    ),
    ObjectDefinition(
        object_type=ObjectType.PAYMENT_METHOD, description="Payment method (card, wallet, ...)."
    ),
    ObjectDefinition(object_type=ObjectType.BENEFIT, description="A discount / benefit."),
    ObjectDefinition(
        object_type=ObjectType.PAYMENT_CHANNEL, description="Upstream payment channel."
    ),
    ObjectDefinition(object_type=ObjectType.PAYMENT_EVENT, description="Canonical payment event."),
    ObjectDefinition(object_type=ObjectType.INCIDENT, description="A conversion anomaly incident."),
    ObjectDefinition(object_type=ObjectType.DIAGNOSIS_RUN, description="One diagnosis execution."),
    ObjectDefinition(object_type=ObjectType.EVIDENCE, description="Deterministic evidence."),
    ObjectDefinition(
        object_type=ObjectType.DIAGNOSIS_REPORT, description="Final diagnosis report."
    ),
    ObjectDefinition(
        object_type=ObjectType.EVALUATION_RUN, description="One evaluation execution."
    ),
]

_LINKS: list[LinkDefinition] = [
    LinkDefinition(
        link_type=LinkType.CONTAINS, source=ObjectType.PURCHASE_INTENT, target=ObjectType.ORDER
    ),
    LinkDefinition(
        link_type=LinkType.OPENS, source=ObjectType.ORDER, target=ObjectType.CHECKOUT_SESSION
    ),
    LinkDefinition(
        link_type=LinkType.CREATES, source=ObjectType.ORDER, target=ObjectType.PAYMENT_ATTEMPT
    ),
    LinkDefinition(
        link_type=LinkType.USES, source=ObjectType.PAYMENT_ATTEMPT, target=ObjectType.PAYMENT_METHOD
    ),
    LinkDefinition(
        link_type=LinkType.ROUTED_TO,
        source=ObjectType.PAYMENT_ATTEMPT,
        target=ObjectType.PAYMENT_CHANNEL,
    ),
    LinkDefinition(
        link_type=LinkType.AFFECTS, source=ObjectType.INCIDENT, target=ObjectType.PURCHASE_INTENT
    ),
    LinkDefinition(
        link_type=LinkType.AFFECTS, source=ObjectType.INCIDENT, target=ObjectType.PAYMENT_ATTEMPT
    ),
    LinkDefinition(
        link_type=LinkType.SUPPORTED_BY,
        source=ObjectType.DIAGNOSIS_REPORT,
        target=ObjectType.EVIDENCE,
    ),
    LinkDefinition(
        link_type=LinkType.EVALUATES,
        source=ObjectType.EVALUATION_RUN,
        target=ObjectType.DIAGNOSIS_RUN,
    ),
]

_METRICS: list[MetricDefinition] = [
    MetricDefinition(
        name="reached_count", description="Intents reaching a funnel stage.", unit="count"
    ),
    MetricDefinition(
        name="stage_conversion_rate", description="Adjacent-stage conversion rate.", unit="ratio"
    ),
    MetricDefinition(
        name="overall_conversion_rate", description="Conversion vs ORDER_CONFIRMED.", unit="ratio"
    ),
    MetricDefinition(name="rate_delta", description="Incident minus baseline rate.", unit="ratio"),
    MetricDefinition(
        name="estimated_lost_intents",
        description="Observational lost intents estimate.",
        unit="count",
    ),
    MetricDefinition(
        name="benefit_gap_minor",
        description="selected_payable - best_payable (minor units).",
        unit="minor",
    ),
    MetricDefinition(
        name="cancel_rate", description="Cancellation rate within a gap bucket.", unit="ratio"
    ),
    MetricDefinition(name="timeout_rate", description="Channel timeout rate.", unit="ratio"),
    MetricDefinition(name="latency_p95_ms", description="P95 latency.", unit="ms"),
]

_DIMENSIONS: list[DimensionDefinition] = [
    DimensionDefinition(name="payment_method", description="Payment method dimension."),
    DimensionDefinition(name="payment_channel", description="Payment channel dimension."),
    DimensionDefinition(name="region", description="Region dimension."),
    DimensionDefinition(name="currency", description="Currency dimension."),
    DimensionDefinition(name="client_version", description="Client version dimension."),
]

_ACTIONS: list[ActionDefinition] = [
    ActionDefinition(
        action_type=ActionType.CREATE_INCIDENT,
        description="Create an incident.",
        exposed_to_frontend=True,
    ),
    ActionDefinition(
        action_type=ActionType.RUN_DIAGNOSIS, description="Run diagnosis.", exposed_to_frontend=True
    ),
    ActionDefinition(
        action_type=ActionType.RETRY_DIAGNOSIS,
        description="Retry diagnosis.",
        exposed_to_frontend=True,
    ),
    ActionDefinition(
        action_type=ActionType.REQUEST_DATA,
        description="Request more data.",
        exposed_to_frontend=False,
    ),
    ActionDefinition(
        action_type=ActionType.ACCEPT_CAUSE,
        description="Accept a root cause.",
        exposed_to_frontend=False,
    ),
    ActionDefinition(
        action_type=ActionType.REJECT_CAUSE,
        description="Reject a root cause.",
        exposed_to_frontend=False,
    ),
    ActionDefinition(
        action_type=ActionType.RESOLVE_INCIDENT,
        description="Resolve an incident.",
        exposed_to_frontend=False,
    ),
]

_EVIDENCE_TYPES: list[EvidenceTypeDefinition] = [
    EvidenceTypeDefinition(
        evidence_type=EvidenceType.FUNNEL_STAGE_DEGRADATION,
        description="A funnel stage degraded vs baseline.",
    ),
    EvidenceTypeDefinition(
        evidence_type=EvidenceType.DIMENSION_CONTRIBUTION,
        description="A dimension contributes disproportionately to loss.",
    ),
    EvidenceTypeDefinition(
        evidence_type=EvidenceType.BENEFIT_GAP_FRICTION,
        description="Benefit gap correlates with friction (not causal proof).",
    ),
    EvidenceTypeDefinition(
        evidence_type=EvidenceType.CHANNEL_TIMEOUT, description="Channel timeouts and latency rose."
    ),
    EvidenceTypeDefinition(
        evidence_type=EvidenceType.ERROR_CODE_CONCENTRATION,
        description="Errors concentrated on specific codes.",
    ),
    EvidenceTypeDefinition(
        evidence_type=EvidenceType.DATA_GAP, description="Required events or fields are missing."
    ),
]


def _validate_links(objects: list[ObjectDefinition], links: list[LinkDefinition]) -> None:
    known = {o.object_type for o in objects}
    for link in links:
        if link.source not in known:
            msg = f"Link {link.link_type} has unknown source {link.source}"
            raise ValueError(msg)
        if link.target not in known:
            msg = f"Link {link.link_type} has unknown target {link.target}"
            raise ValueError(msg)


def build_registry() -> OntologyRegistry:
    """Construct and validate the v1 registry."""
    _validate_links(_OBJECTS, _LINKS)
    return OntologyRegistry(
        objects=_OBJECTS,
        links=_LINKS,
        metrics=_METRICS,
        dimensions=_DIMENSIONS,
        actions=_ACTIONS,
        evidence_types=_EVIDENCE_TYPES,
    )


# Module-level singleton, validated at import time (plan § 7.2 "启动时校验").
REGISTRY: OntologyRegistry = build_registry()


def registry_json_schema() -> dict:
    """JSON Schema of the registry, for API docs and frontend use."""
    return OntologyRegistry.model_json_schema()
