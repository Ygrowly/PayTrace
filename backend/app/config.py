"""Runtime configuration loaded from environment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Look for .env in the current working directory first, then fall back to
    # the monorepo root. This lets `uv run alembic upgrade head` and `uvicorn`
    # work both when invoked from `backend/` and from the repo root.
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    env: str = "dev"

    # External services.
    database_url: str = "postgresql+psycopg://paytrace:paytrace_dev@localhost:54320/paytrace"
    redis_url: str = "redis://localhost:6379/0"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "paytrace"
    minio_secret_key: str = "paytrace_dev_secret"  # noqa: S105 - dev default, not a real secret
    minio_bucket: str = "paytrace"
    minio_secure: bool = False

    # Local runtime roots used by the deterministic harness and M3 report
    # artifacts. Relative values are resolved from the monorepo root.
    scenario_root: str = "data/scenarios"
    artifact_root: str = "data/artifacts"

    # API.
    api_host: str = "0.0.0.0"  # noqa: S104 - binding all interfaces is intentional for local dev
    api_port: int = 8000
    frontend_origin: str = "http://localhost:3000"

    # Celery.
    celery_concurrency: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
