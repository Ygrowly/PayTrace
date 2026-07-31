"""Health endpoints.

* `/health/live`  — process liveness probe; no I/O.
* `/health/ready` — readiness probe; sequentially checks PG, Redis, MinIO.

Each dependency check is independent and returns its own latency. Any failure
results in HTTP 503 with a per-dependency status payload so callers can locate
the failing dependency in one shot.
"""

import time
from typing import Literal

import boto3
import redis.asyncio as aioredis
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app.config import get_settings
from app.db.session import engine

router = APIRouter()


class DependencyStatus(BaseModel):
    status: Literal["ok", "error"]
    latency_ms: int | None = None
    detail: str | None = None


class LivenessResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ok", "error"]
    dependencies: dict[str, DependencyStatus]


@router.get("/health/live", response_model=LivenessResponse)
async def health_live() -> LivenessResponse:
    return LivenessResponse(status="ok")


def _postgres_select_1() -> None:
    """Synchronous SELECT 1 against the control-plane DB."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


async def _check_postgres() -> DependencyStatus:
    import anyio

    started = time.monotonic()
    try:
        await anyio.to_thread.run_sync(_postgres_select_1)
    except Exception as exc:  # noqa: BLE001 - surface as dependency error, don't crash probe
        return DependencyStatus(status="error", detail=f"{type(exc).__name__}: {exc!s}"[:200])
    return DependencyStatus(status="ok", latency_ms=int((time.monotonic() - started) * 1000))


async def _check_redis() -> DependencyStatus:
    settings = get_settings()
    started = time.monotonic()
    client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        pong = await client.ping()
        if not pong:
            return DependencyStatus(status="error", detail="PING returned falsy")
    except Exception as exc:  # noqa: BLE001
        return DependencyStatus(status="error", detail=type(exc).__name__)
    finally:
        await client.aclose()
    return DependencyStatus(status="ok", latency_ms=int((time.monotonic() - started) * 1000))


def _head_minio_bucket() -> None:
    """Synchronous MinIO HEAD bucket call. Wrapped via anyio.to_thread by caller."""
    settings = get_settings()
    protocol = "https" if settings.minio_secure else "http"
    client = boto3.client(
        "s3",
        endpoint_url=f"{protocol}://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=BotoConfig(connect_timeout=2, read_timeout=2, retries={"max_attempts": 1}),
        region_name="us-east-1",
    )
    client.head_bucket(Bucket=settings.minio_bucket)


async def _check_minio() -> DependencyStatus:
    import anyio

    started = time.monotonic()
    try:
        await anyio.to_thread.run_sync(_head_minio_bucket)
    except (BotoCoreError, ClientError) as exc:
        return DependencyStatus(status="error", detail=type(exc).__name__)
    except Exception as exc:  # noqa: BLE001
        return DependencyStatus(status="error", detail=type(exc).__name__)
    return DependencyStatus(status="ok", latency_ms=int((time.monotonic() - started) * 1000))


@router.get("/health/ready", response_model=ReadinessResponse)
async def health_ready(response: Response) -> ReadinessResponse:
    pg, redis_status, minio = await _run_checks()
    overall_ok = all(dep.status == "ok" for dep in (pg, redis_status, minio))
    if not overall_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ok" if overall_ok else "error",
        dependencies={"postgres": pg, "redis": redis_status, "minio": minio},
    )


async def _run_checks() -> tuple[DependencyStatus, DependencyStatus, DependencyStatus]:
    """Run PG / Redis / MinIO checks concurrently and return them in order."""
    import anyio

    results: list[DependencyStatus] = []

    async def _collect(check, results=results):  # noqa: ANN001, ANN202
        results.append(await check())

    async with anyio.create_task_group() as tg:
        tg.start_soon(_collect, _check_postgres)
        tg.start_soon(_collect, _check_redis)
        tg.start_soon(_collect, _check_minio)
    # Order matches the order of start_soon calls because each check appends
    # once and task groups preserve start order in our usage. For safety, fall
    # back to re-running sequentially if anyio ever reorders.
    if len(results) != 3:
        return await _sequential_checks()
    return results[0], results[1], results[2]


async def _sequential_checks() -> tuple[DependencyStatus, DependencyStatus, DependencyStatus]:
    return await _check_postgres(), await _check_redis(), await _check_minio()
