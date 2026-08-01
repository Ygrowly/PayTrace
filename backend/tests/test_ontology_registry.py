"""Unit tests for the Ontology v1 registry (plan § 7)."""

import pytest

from app.ontology.registry import (
    REGISTRY,
    ActionType,
    EvidenceType,
    LinkDefinition,
    LinkType,
    ObjectType,
    _validate_links,
    registry_json_schema,
)


def test_registry_version_fixed():
    assert REGISTRY.version == "paytrace.ontology.v1"


def test_registry_has_thirteen_objects():
    assert len(REGISTRY.objects) == 13
    object_types = {o.object_type for o in REGISTRY.objects}
    assert ObjectType.PURCHASE_INTENT in object_types
    assert ObjectType.EVIDENCE in object_types
    assert ObjectType.EVALUATION_RUN in object_types


def test_registry_links_reference_known_objects():
    # _validate_links ran at import; confirm key links exist.
    pairs = {(link.link_type, link.source, link.target) for link in REGISTRY.links}
    assert (LinkType.CONTAINS, ObjectType.PURCHASE_INTENT, ObjectType.ORDER) in pairs
    assert (LinkType.SUPPORTED_BY, ObjectType.DIAGNOSIS_REPORT, ObjectType.EVIDENCE) in pairs
    assert (LinkType.EVALUATES, ObjectType.EVALUATION_RUN, ObjectType.DIAGNOSIS_RUN) in pairs


def test_validate_links_rejects_unknown_source():
    bad = [
        LinkDefinition(
            link_type=LinkType.CONTAINS,
            source=ObjectType.PURCHASE_INTENT,
            target=ObjectType.ORDER,
        )
    ]
    with pytest.raises(ValueError, match="unknown source"):
        _validate_links([], bad)


def test_frontend_actions_limited_to_three():
    frontend = REGISTRY.frontend_action_types()
    assert frontend == {
        ActionType.CREATE_INCIDENT,
        ActionType.RUN_DIAGNOSIS,
        ActionType.RETRY_DIAGNOSIS,
    }


def test_dimension_whitelist_matches_plan():
    assert REGISTRY.dimension_names() == {
        "payment_method",
        "payment_channel",
        "region",
        "currency",
        "client_version",
    }


def test_evidence_types_complete():
    types = {e.evidence_type for e in REGISTRY.evidence_types}
    assert EvidenceType.BENEFIT_GAP_FRICTION in types
    assert EvidenceType.CHANNEL_TIMEOUT in types
    assert EvidenceType.DATA_GAP in types


def test_registry_frozen():
    with pytest.raises(Exception):  # noqa: B017 - frozen model raises ValidationError
        REGISTRY.version = "paytrace.ontology.v2"  # type: ignore[misc]


def test_json_schema_generated():
    schema = registry_json_schema()
    assert schema["title"] == "OntologyRegistry"
    assert "objects" in schema["properties"]
