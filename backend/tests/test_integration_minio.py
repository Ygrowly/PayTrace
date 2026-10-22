"""Integration test: large tool results stored in MinIO (M1 acceptance).

Requires the local docker-compose MinIO (paytrace-minio). Skips cleanly when
MinIO is unreachable so unit-only runs stay green.
"""

import json

import pytest

from app.analytics.duckdb_source import DuckDBAnalyticsSource
from app.config import get_settings
from app.harness.artifact_store import MinioArtifactStore
from app.harness.scenarios.generator import ScenarioConfig, generate_scenario
from app.harness.scenarios.io import write_dataset
from app.tools.base import EvidenceLedger, ToolPolicy, ToolRegistry
from app.tools.diagnostic import build_default_tools


def _minio_reachable() -> bool:
    try:
        store = MinioArtifactStore()
        store._client.list_buckets()
        return True
    except Exception:  # noqa: BLE001 - any connection failure means skip
        return False


pytestmark = pytest.mark.skipif(not _minio_reachable(), reason="MinIO not reachable")


@pytest.fixture(scope="module")
def minio_store():
    store = MinioArtifactStore()
    # Ensure the bucket exists (idempotent).
    try:
        store._client.create_bucket(Bucket=store._bucket)
    except Exception:  # noqa: BLE001, S110 - BucketAlreadyOwnedByYou etc.; idempotent setup
        pass
    return store


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    events, _ = generate_scenario(ScenarioConfig(kind="mixed_failure", seed=42, num_intents=2000))
    return write_dataset(events, tmp_path_factory.mktemp("ds"), "mixed_failure")


def test_large_tool_result_stored_in_minio(minio_store, dataset):
    """Full funnel tool result (all stage deltas) lands in MinIO and round-trips."""
    source = DuckDBAnalyticsSource()
    registry = ToolRegistry()
    for tool in build_default_tools(source, minio_store):
        registry.register(tool)

    policy = ToolPolicy()
    ledger = EvidenceLedger()
    result = registry.execute("accept-1", "get_payment_funnel", policy, dataset_ref=dataset.path)
    ledger.record_result(result)

    assert result.artifact_ref is not None
    assert result.artifact_ref.bucket == get_settings().minio_bucket

    # Round-trip the artifact bytes from real MinIO and verify content.
    payload = json.loads(minio_store.get_bytes(result.artifact_ref))
    assert "anomalous_stages" in payload
    assert "deltas" in payload
    assert len(payload["deltas"]) == 9  # 9 funnel stages

    # Presigned download URL is generated.
    url = minio_store.create_download_url(result.artifact_ref, expires_seconds=60)
    assert url.startswith("http")
    assert result.artifact_ref.key in url


def test_mixed_failure_dual_evidence_via_minio(minio_store, dataset):
    """M1 acceptance: mixed_failure yields benefit-friction + channel-timeout evidence."""
    source = DuckDBAnalyticsSource()
    registry = ToolRegistry()
    for tool in build_default_tools(source, minio_store):
        registry.register(tool)

    policy = ToolPolicy()
    ledger = EvidenceLedger()
    r1 = registry.execute("a1", "analyze_benefit_gap", policy, dataset_ref=dataset.path)
    r2 = registry.execute("a2", "inspect_payment_events", policy, dataset_ref=dataset.path)
    for r in (r1, r2):
        ledger.record_result(r)

    from app.ontology.registry import EvidenceType

    types = {e.evidence_type for e in ledger.all()}
    assert EvidenceType.BENEFIT_GAP_FRICTION in types
    assert EvidenceType.CHANNEL_TIMEOUT in types
