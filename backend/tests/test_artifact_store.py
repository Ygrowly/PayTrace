"""Unit tests for ArtifactStore (LocalArtifactStore + key sanitisation)."""

import pytest

from app.harness.artifact_store import (
    ArtifactChecksumError,
    ArtifactRef,
    LocalArtifactStore,
    _sanitize_key,
)


def test_sanitize_key_strips_unsafe_chars():
    assert _sanitize_key("runs/abc/def.json") == "runs/abc/def.json"
    assert _sanitize_key("runs/a b/c?.json") == "runs/a_b/c_.json"


def test_sanitize_key_forbids_traversal():
    assert _sanitize_key("../etc/passwd") == "etc/passwd"
    assert _sanitize_key("a/../../b") == "a/b"


def test_sanitize_key_rejects_empty():
    with pytest.raises(ValueError, match="at least one path segment"):
        _sanitize_key("../..")


def test_local_store_roundtrip(tmp_path):
    store = LocalArtifactStore(tmp_path)
    payload = b'{"rows": [1, 2, 3]}'
    ref = store.put_bytes("tool_results/run-1/funnel.json", payload, "application/json")
    assert ref.bucket == "local"
    assert ref.size_bytes == len(payload)
    assert len(ref.checksum_sha256) == 64
    assert store.get_bytes(ref) == payload


def test_local_store_checksum_detects_tamper(tmp_path):
    store = LocalArtifactStore(tmp_path)
    ref = store.put_bytes("a/b.bin", b"original", "application/octet-stream")
    # Corrupt the on-disk bytes after the ref was created.
    (tmp_path / "a" / "b.bin").write_bytes(b"tampered")
    with pytest.raises(ArtifactChecksumError):
        store.get_bytes(ref)


def test_local_store_traversal_neutralised_inside_root(tmp_path):
    store = LocalArtifactStore(tmp_path)
    # "../.." segments are stripped by _sanitize_key, so the write lands
    # inside the store root rather than escaping it.
    ref = store.put_bytes("../../outside.bin", b"x", "application/octet-stream")
    assert ref.key == "outside.bin"
    assert (tmp_path / "outside.bin").read_bytes() == b"x"
    assert not (tmp_path.parent / "outside.bin").exists()


def test_local_store_rejects_pure_traversal_key(tmp_path):
    store = LocalArtifactStore(tmp_path)
    with pytest.raises(ValueError, match="at least one path segment"):
        store.put_bytes("../..", b"x", "application/octet-stream")


def test_local_store_download_url_is_file_uri(tmp_path):
    store = LocalArtifactStore(tmp_path)
    ref = store.put_bytes("x.txt", b"hi", "text/plain")
    url = store.create_download_url(ref, expires_seconds=60)
    assert url.startswith("file://")


def test_artifact_ref_frozen():
    ref = ArtifactRef(
        bucket="b",
        key="k",
        checksum_sha256="0" * 64,
        size_bytes=1,
        content_type="text/plain",
    )
    with pytest.raises(Exception):  # noqa: B017
        ref.key = "other"  # type: ignore[misc]
