"""Ontology API (plan § 7). Serves the validated v1 registry."""

from fastapi import APIRouter

from app.ontology.registry import REGISTRY, OntologyRegistry

router = APIRouter()


@router.get("/ontology", response_model=OntologyRegistry)
async def get_ontology() -> OntologyRegistry:
    """Return the full v1 Ontology registry (objects, links, metrics,
    dimensions, actions, evidence types)."""
    return REGISTRY
