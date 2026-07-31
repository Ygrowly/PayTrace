"""v1 API router aggregator."""

from fastapi import APIRouter

from app.api.v1 import health, ontology

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health.router, tags=["system"])
api_v1_router.include_router(ontology.router, tags=["ontology"])
