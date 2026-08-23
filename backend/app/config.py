"""Runtime configuration loaded from environment."""

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Look for .env in the current working directory first, then fall back to
    # the monorepo root. This lets `uv run alembic upgrade head` and `uvicorn`
    # work both when invoked from `backend/` and from the repo root.
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    app_env: Literal["dev", "test", "staging", "production"] = "dev"

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
    artifact_store_backend: Literal["local", "minio"] = "local"

    # API.
    api_host: str = "0.0.0.0"  # noqa: S104 - binding all interfaces is intentional for local dev
    api_port: int = 8000
    frontend_origin: str = "http://localhost:3000"
    trusted_hosts: list[str] = ["localhost", "127.0.0.1", "test", "testserver"]

    # Celery.
    celery_concurrency: int = 2

    # Model provider (plan § 15.2).
    model_provider: str = "rule_based"
    model_base_url: str = ""
    model_api_key: str = ""
    model_name: str = ""

    # Diagnostic harness budget (plan § 14.3).
    tool_timeout_seconds: int = 15
    max_tool_calls: int = 8

    @model_validator(mode="after")
    def reject_insecure_deployment_defaults(self) -> "Settings":
        """Fail fast when staging/production uses local development defaults."""
        if self.app_env not in {"staging", "production"}:
            return self

        problems: list[str] = []
        database = urlsplit(self.database_url)
        if database.password in {None, "", "paytrace_dev"}:
            problems.append("DATABASE_URL must use a non-development password")
        if self.minio_secret_key == "paytrace_dev_secret":  # noqa: S105 - detect dev default
            problems.append("MINIO_SECRET_KEY must not use the development default")
        if self.artifact_store_backend != "minio":
            problems.append("ARTIFACT_STORE_BACKEND must be minio")
        frontend = urlsplit(self.frontend_origin)
        if frontend.scheme != "https" or frontend.hostname in {"localhost", "127.0.0.1", "::1"}:
            problems.append("FRONTEND_ORIGIN must be a public HTTPS origin")
        if not self.trusted_hosts or "*" in self.trusted_hosts:
            problems.append("TRUSTED_HOSTS must contain explicit API hostnames")
        if problems:
            raise ValueError("insecure deployment configuration: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
