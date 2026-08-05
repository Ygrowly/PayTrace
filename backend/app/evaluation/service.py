"""Persistence and state transitions for EvaluationRun."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import EvaluationRun
from app.evaluation.models import EvaluationReport

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"DISPATCH_FAILED", "QUEUED", "CANCELLED"},
    "DISPATCH_FAILED": {"QUEUED", "CANCELLED"},
    "QUEUED": {"RUNNING", "FAILED", "DISPATCH_FAILED", "CANCELLED"},
    "RUNNING": {"SUCCEEDED", "FAILED", "CANCELLED"},
}
_TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "CANCELLED"}


def create_or_get(
    db: Session,
    *,
    idempotency_key: str,
    model_mode: str,
    prompt_version: str | None,
    scenario_kinds: list[str],
    seed: int,
    num_intents: int,
    ontology_version: str,
) -> tuple[EvaluationRun, bool]:
    """Create one evaluation or return the existing idempotent request."""
    now = datetime.now(UTC)
    run_id = uuid.uuid4()
    stmt = (
        pg_insert(EvaluationRun)
        .values(
            id=run_id,
            idempotency_key=idempotency_key,
            status="PENDING",
            model_mode=model_mode,
            model_name="RuleBasedModelAdapter" if model_mode == "B0" else None,
            prompt_version=prompt_version,
            ontology_version=ontology_version,
            scenario_kinds=scenario_kinds,
            scenario_count=len(scenario_kinds),
            seed=seed,
            num_intents=num_intents,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(EvaluationRun.id)
    )
    row = db.execute(stmt).fetchone()
    if row is not None:
        db.flush()
        run = db.query(EvaluationRun).filter(EvaluationRun.id == run_id).first()
        if run is None:  # pragma: no cover - database returned the inserted id
            raise RuntimeError("evaluation insert returned no row")
        return run, True

    existing = (
        db.query(EvaluationRun).filter(EvaluationRun.idempotency_key == idempotency_key).first()
    )
    if existing is None:
        raise RuntimeError("evaluation idempotency conflict but existing row not found")
    return existing, False


def get(db: Session, evaluation_run_id: uuid.UUID) -> EvaluationRun | None:
    return db.query(EvaluationRun).filter(EvaluationRun.id == evaluation_run_id).first()


def list_runs(
    db: Session, *, page: int = 1, page_size: int = 20
) -> tuple[list[EvaluationRun], int]:
    query = db.query(EvaluationRun)
    total = query.count()
    items = (
        query.order_by(EvaluationRun.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def update_status(db: Session, run: EvaluationRun, new_status: str, **extra_fields: Any) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(run.status, set())
    if new_status != run.status and new_status not in allowed:
        raise ValueError(f"Invalid evaluation state transition: {run.status} -> {new_status}")

    run.status = new_status
    now = datetime.now(UTC)
    if new_status == "RUNNING" and run.started_at is None:
        run.started_at = now
    if new_status in _TERMINAL_STATUSES and run.finished_at is None:
        run.finished_at = now
    for key, value in extra_fields.items():
        if hasattr(run, key):
            setattr(run, key, value)
    if run.started_at and run.finished_at and run.total_duration_ms is None:
        run.total_duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
    run.updated_at = now
    db.flush()


def persist_report(db: Session, run: EvaluationRun, report: EvaluationReport) -> None:
    run.metrics = report.metrics.model_dump(mode="json")
    run.scenario_results = [item.model_dump(mode="json") for item in report.scenario_results]
    run.badcases = report.badcases
    run.ontology_version = report.ontology_version
    run.scenario_count = report.metrics.scenario_count
    run.updated_at = datetime.now(UTC)
    db.flush()


__all__ = [
    "create_or_get",
    "get",
    "list_runs",
    "persist_report",
    "update_status",
]
