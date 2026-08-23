"""Celery task for the deterministic M3 Evaluation Runner."""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from typing import Any

from app.config import get_settings
from app.db.models import ArtifactRecord
from app.db.session import session_maker
from app.evaluation import service
from app.evaluation.runner import resolve_runtime_path, run_evaluation
from app.harness.artifact_store import create_artifact_store
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@contextmanager
def _db():
    session = session_maker()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _artifact_record(*, run_id: uuid.UUID, artifact_type: str, ref: Any) -> ArtifactRecord:
    return ArtifactRecord(
        evaluation_run_id=run_id,
        artifact_type=artifact_type,
        storage_backend=ref.backend,
        storage_bucket=ref.bucket,
        storage_key=ref.key,
        content_type=ref.content_type,
        size_bytes=ref.size_bytes,
        checksum=ref.checksum_sha256,
    )


@celery_app.task(
    name="app.tasks.evaluation.run_evaluation",
    bind=True,
    max_retries=0,
    acks_late=False,
    soft_time_limit=300,  # seconds — evaluation runs multiple scenarios
    time_limit=420,  # seconds — hard kill
)
def run_evaluation_task(self: Any, evaluation_run_id: str) -> dict[str, str]:
    """Execute one EvaluationRun and persist report artifacts/results."""
    del self  # Celery bind is retained for a stable task contract.
    run_id = uuid.UUID(evaluation_run_id)
    settings = get_settings()
    logger.info("run_evaluation starting run_id=%s", run_id)

    with _db() as db:
        run = service.get(db, run_id)
        if run is None:
            logger.error("run_evaluation: run not found run_id=%s", run_id)
            return {"run_id": str(run_id), "status": "NOT_FOUND"}
        if run.status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return {"run_id": str(run_id), "status": run.status}
        service.update_status(db, run, "RUNNING")

    artifact_store = create_artifact_store(settings)
    try:
        execution = run_evaluation(
            evaluation_run_id=str(run_id),
            model_mode=run.model_mode,
            prompt_version=run.prompt_version,
            scenario_kinds=run.scenario_kinds,
            seed=run.seed,
            num_intents=run.num_intents,
            scenario_root=resolve_runtime_path(settings.scenario_root),
            artifacts=artifact_store,
        )
        json_ref = artifact_store.put_bytes(
            f"evaluation_reports/{run_id}/report.json",
            execution.json_bytes,
            "application/json",
        )
        markdown_ref = artifact_store.put_bytes(
            f"evaluation_reports/{run_id}/report.md",
            execution.markdown_bytes,
            "text/markdown; charset=utf-8",
        )
    except Exception as exc:  # noqa: BLE001 - status must make the failure visible
        logger.exception("run_evaluation failed run_id=%s", run_id)
        with _db() as db:
            run = service.get(db, run_id)
            if run is not None:
                service.update_status(
                    db,
                    run,
                    "FAILED",
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:2048],
                )
        return {"run_id": str(run_id), "status": "FAILED"}

    with _db() as db:
        run = service.get(db, run_id)
        if run is None:
            return {"run_id": str(run_id), "status": "NOT_FOUND"}
        db.add(
            _artifact_record(run_id=run_id, artifact_type="evaluation_report_json", ref=json_ref)
        )
        db.add(
            _artifact_record(
                run_id=run_id, artifact_type="evaluation_report_markdown", ref=markdown_ref
            )
        )
        service.persist_report(db, run, execution.report)
        service.update_status(
            db,
            run,
            "SUCCEEDED",
            report_json_key=json_ref.key,
            report_markdown_key=markdown_ref.key,
        )

    logger.info("run_evaluation done run_id=%s", run_id)
    return {"run_id": str(run_id), "status": "SUCCEEDED"}


__all__ = ["run_evaluation_task"]
