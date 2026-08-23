"""Runtime configuration safety tests."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def _production_settings(**overrides):  # noqa: ANN003, ANN202
    values = {
        "app_env": "production",
        "database_url": "postgresql+psycopg://paytrace:strong-db-password@postgres/paytrace",
        "minio_secret_key": "strong-minio-password",
        "artifact_store_backend": "minio",
        "frontend_origin": "https://paytrace.example.com",
        "trusted_hosts": ["api.paytrace.example.com"],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_development_defaults_remain_valid():
    settings = Settings(_env_file=None)
    assert settings.app_env == "dev"


def test_production_configuration_accepts_non_default_secrets():
    settings = _production_settings()
    assert settings.app_env == "production"
    assert settings.artifact_store_backend == "minio"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        (
            {"database_url": "postgresql+psycopg://paytrace:paytrace_dev@postgres/paytrace"},
            "DATABASE_URL",
        ),
        ({"minio_secret_key": "paytrace_dev_secret"}, "MINIO_SECRET_KEY"),
        ({"artifact_store_backend": "local"}, "ARTIFACT_STORE_BACKEND"),
        ({"frontend_origin": "http://localhost:3000"}, "FRONTEND_ORIGIN"),
        ({"trusted_hosts": ["*"]}, "TRUSTED_HOSTS"),
    ],
)
def test_production_configuration_rejects_insecure_defaults(override, message):  # noqa: ANN001
    with pytest.raises(ValidationError, match=message):
        _production_settings(**override)


def test_staging_uses_the_same_safety_gate():
    with pytest.raises(ValidationError, match="ARTIFACT_STORE_BACKEND"):
        _production_settings(app_env="staging", artifact_store_backend="local")
