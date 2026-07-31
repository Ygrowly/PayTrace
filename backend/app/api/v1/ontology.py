"""Ontology placeholder (plan § M0b). Real Ontology v1 ships in M1."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class OntologyPlaceholder(BaseModel):
    version: str
    note: str


@router.get("/ontology", response_model=OntologyPlaceholder)
async def get_ontology() -> OntologyPlaceholder:
    return OntologyPlaceholder(
        version="v0-placeholder",
        note="Ontology v1 will be introduced in M1 per plan § 7.",
    )
