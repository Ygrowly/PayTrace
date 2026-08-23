"""ArtifactStore protocol and implementations (plan § 11).

Stores full tool results, large drill-down tables, raw model responses,
evaluation reports, trace exports and data-quality reports. The DB keeps only
metadata + references; model context carries only summaries + artifact IDs.

Constraints implemented here:
- content is checksum-verified (SHA-256);
- download URLs are short-lived (MinIO presigned);
- storage keys never contain raw user input paths — callers pass a logical
  key which is namespaced and sanitised.
"""

import hashlib
import re
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel

from app.config import Settings, get_settings


class ArtifactRef(BaseModel):
    """Reference to a stored artifact. Persisted in the control-plane DB."""

    backend: Literal["local", "minio"]
    bucket: str
    key: str
    checksum_sha256: str
    size_bytes: int
    content_type: str

    model_config = {"frozen": True}


@runtime_checkable
class ArtifactStore(Protocol):
    def put_bytes(self, key: str, data: bytes, content_type: str) -> ArtifactRef: ...
    def get_bytes(self, ref: ArtifactRef) -> bytes: ...
    def create_download_url(self, ref: ArtifactRef, expires_seconds: int) -> str: ...


_SAFE_KEY = re.compile(r"[^A-Za-z0-9._/-]")


def _sanitize_key(key: str) -> str:
    """Strip anything outside a conservative whitelist and forbid traversal."""
    cleaned = _SAFE_KEY.sub("_", key)
    parts = [p for p in cleaned.split("/") if p not in ("", ".", "..")]
    if not parts:
        msg = "artifact key must contain at least one path segment"
        raise ValueError(msg)
    return "/".join(parts)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ArtifactChecksumError(Exception):
    """Raised when stored bytes do not match the recorded checksum."""


class ArtifactStoreError(Exception):
    """Raised when artifact bytes or a download URL cannot be accessed."""


class MinioArtifactStore:
    """MinIO-backed store for local and integration environments."""

    def __init__(self, bucket: str | None = None, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self._bucket = bucket or settings.minio_bucket
        protocol = "https" if settings.minio_secure else "http"
        self._client = boto3.client(
            "s3",
            endpoint_url=f"{protocol}://{settings.minio_endpoint}",
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            config=BotoConfig(connect_timeout=5, read_timeout=30, retries={"max_attempts": 2}),
            region_name="us-east-1",
        )

    def put_bytes(self, key: str, data: bytes, content_type: str) -> ArtifactRef:
        safe = _sanitize_key(key)
        checksum = _sha256(data)
        self._client.put_object(
            Bucket=self._bucket,
            Key=safe,
            Body=data,
            ContentType=content_type,
            Metadata={"sha256": checksum},
        )
        return ArtifactRef(
            backend="minio",
            bucket=self._bucket,
            key=safe,
            checksum_sha256=checksum,
            size_bytes=len(data),
            content_type=content_type,
        )

    def get_bytes(self, ref: ArtifactRef) -> bytes:
        try:
            resp = self._client.get_object(Bucket=ref.bucket, Key=ref.key)
            data = resp["Body"].read()
        except (BotoCoreError, ClientError) as exc:
            raise ArtifactStoreError(f"cannot read minio artifact {ref.bucket}/{ref.key}") from exc
        if _sha256(data) != ref.checksum_sha256:
            msg = f"checksum mismatch for {ref.bucket}/{ref.key}"
            raise ArtifactChecksumError(msg)
        return data

    def create_download_url(self, ref: ArtifactRef, expires_seconds: int) -> str:
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": ref.bucket, "Key": ref.key},
                ExpiresIn=expires_seconds,
            )
        except (BotoCoreError, ClientError) as exc:
            raise ArtifactStoreError(
                f"cannot create minio download URL for {ref.bucket}/{ref.key}"
            ) from exc


class LocalArtifactStore:
    """Filesystem-backed store for unit tests and offline scripts only."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        safe = _sanitize_key(key)
        path = (self._root / safe).resolve()
        if self._root.resolve() not in path.parents and path != self._root.resolve():
            msg = f"resolved path escapes store root: {key}"
            raise ValueError(msg)
        return path

    def put_bytes(self, key: str, data: bytes, content_type: str) -> ArtifactRef:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return ArtifactRef(
            backend="local",
            bucket="local",
            key=_sanitize_key(key),
            checksum_sha256=_sha256(data),
            size_bytes=len(data),
            content_type=content_type,
        )

    def get_bytes(self, ref: ArtifactRef) -> bytes:
        try:
            data = self._path_for(ref.key).read_bytes()
        except OSError as exc:
            raise ArtifactStoreError(f"cannot read local artifact {ref.key}") from exc
        if _sha256(data) != ref.checksum_sha256:
            msg = f"checksum mismatch for local/{ref.key}"
            raise ArtifactChecksumError(msg)
        return data

    def create_download_url(self, ref: ArtifactRef, expires_seconds: int) -> str:
        # Local store has no real URL; return a file:// URI for offline use.
        path = self._path_for(ref.key)
        if not path.is_file():
            raise ArtifactStoreError(f"cannot read local artifact {ref.key}")
        return f"file://{path}"


def create_artifact_store(
    settings: Settings | None = None,
    *,
    backend: Literal["local", "minio"] | None = None,
) -> ArtifactStore:
    """Create the configured runtime store.

    ``local`` is suitable for offline scripts and single-host development.
    ``minio`` is required when API and worker processes do not share a
    filesystem, including the full Docker Compose topology.
    """
    resolved = settings or get_settings()
    selected_backend = backend or resolved.artifact_store_backend
    if selected_backend == "minio":
        return MinioArtifactStore(settings=resolved)

    root = Path(resolved.artifact_root)
    if not root.is_absolute():
        repo_root = Path(__file__).resolve().parents[3]
        root = (repo_root / root).resolve()
    return LocalArtifactStore(root)
