"""Tests for the tool framework (§ 14.2) and the four diagnosis tools (§ 13)."""

import pytest

from app.analytics.duckdb_source import DuckDBAnalyticsSource
from app.harness.artifact_store import LocalArtifactStore
from app.harness.scenarios.generator import ScenarioConfig, generate_scenario
from app.harness.scenarios.io import write_dataset
from app.ontology.registry import EvidenceType
from app.tools.base import (
    MAX_TOOL_CALLS,
    EvidenceLedger,
    ToolPolicy,
    ToolPolicyViolation,
    ToolRegistry,
)
from app.tools.diagnostic import (
    build_default_tools,
)


@pytest.fixture(scope="module")
def source():
    return DuckDBAnalyticsSource()


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory):
    return LocalArtifactStore(tmp_path_factory.mktemp("artifacts"))


@pytest.fixture(scope="module")
def datasets(tmp_path_factory):
    root = tmp_path_factory.mktemp("datasets")
    refs = {}
    for kind in ("normal", "benefit_friction", "channel_timeout", "mixed_failure", "data_gap"):
        events, _ = generate_scenario(ScenarioConfig(kind=kind, seed=42, num_intents=400))
        refs[kind] = write_dataset(events, root, kind)
    return refs


@pytest.fixture()
def registry(source, artifacts):
    reg = ToolRegistry()
    for tool in build_default_tools(source, artifacts):
        reg.register(tool)
    return reg


# --- Framework -----------------------------------------------------------------


def test_registry_rejects_unregistered(registry):
    with pytest.raises(ToolPolicyViolation, match="unregistered tool"):
        registry.get("drop_table")


def test_registry_rejects_non_read_only():
    class WriteTool:
        name = "writer"
        version = "1"
        read_only = False

        def run(self, tool_call_id, **kw): ...

    reg = ToolRegistry()
    with pytest.raises(ToolPolicyViolation, match="read-only"):
        reg.register(WriteTool())


def test_policy_enforces_call_budget(registry, datasets):
    policy = ToolPolicy(max_calls=2)
    # Distinct filters per call so dedup does not fire before the budget.
    for i, channel in enumerate(("channel_a", "channel_b")):
        registry.execute(
            f"call-{i}",
            "get_payment_funnel",
            policy,
            dataset_ref=datasets["normal"].path,
            filters={"payment_channel": channel},
        )
    with pytest.raises(ToolPolicyViolation, match="budget exhausted"):
        registry.execute(
            "call-2",
            "get_payment_funnel",
            policy,
            dataset_ref=datasets["normal"].path,
            filters={"payment_channel": "channel_c"},
        )


def test_policy_dedupes_identical_calls(registry, datasets):
    policy = ToolPolicy()
    registry.execute("call-0", "get_payment_funnel", policy, dataset_ref=datasets["normal"].path)
    with pytest.raises(ToolPolicyViolation, match="duplicate tool call"):
        registry.execute(
            "call-1", "get_payment_funnel", policy, dataset_ref=datasets["normal"].path
        )


def test_policy_default_budget_is_eight():
    assert MAX_TOOL_CALLS == 8
    policy = ToolPolicy()
    assert policy.call_count == 0


def test_evidence_ledger_assigns_unique_codes(registry, datasets):
    policy = ToolPolicy()
    ledger = EvidenceLedger()
    res = registry.execute(
        "call-0",
        "breakdown_conversion_loss",
        policy,
        dataset_ref=datasets["channel_timeout"].path,
        dimension="payment_channel",
    )
    evs = ledger.record_result(res)
    assert evs, "expected evidence from channel_timeout breakdown"
    codes = [e.evidence_code for e in evs]
    assert len(codes) == len(set(codes))
    assert all(c.startswith("EV-") for c in codes)
    # Ledger summaries expose codes + one-liners, not full metrics.
    assert all("[" in s and "]" in s for s in ledger.summaries())


# --- get_payment_funnel ----------------------------------------------------------


def test_funnel_tool_normal_no_evidence(registry, datasets):
    res = registry.execute(
        "call-0", "get_payment_funnel", ToolPolicy(), dataset_ref=datasets["normal"].path
    )
    assert res.status == "success"
    assert res.evidence == []
    assert "no anomalous" in res.warnings[0]


def test_funnel_tool_channel_timeout_raises_stage_evidence(registry, datasets):
    res = registry.execute(
        "call-0", "get_payment_funnel", ToolPolicy(), dataset_ref=datasets["channel_timeout"].path
    )
    stages = {e.metrics["stage"] for e in res.evidence}
    assert "CHANNEL_SUCCEEDED" in stages
    assert all(e.evidence_type == EvidenceType.FUNNEL_STAGE_DEGRADATION for e in res.evidence)


def test_funnel_tool_stores_artifact(registry, datasets, artifacts):
    res = registry.execute(
        "call-0", "get_payment_funnel", ToolPolicy(), dataset_ref=datasets["mixed_failure"].path
    )
    assert res.artifact_ref is not None
    payload = artifacts.get_bytes(res.artifact_ref)
    assert b"anomalous_stages" in payload


# --- breakdown_conversion_loss ----------------------------------------------------


def test_breakdown_tool_pinpoints_channel_b(registry, datasets):
    res = registry.execute(
        "call-0",
        "breakdown_conversion_loss",
        ToolPolicy(),
        dataset_ref=datasets["channel_timeout"].path,
        dimension="payment_channel",
    )
    assert res.evidence, "expected dimension contribution evidence"
    top = res.evidence[0]
    assert top.dimensions == {"payment_channel": "channel_b"}
    assert top.evidence_type == EvidenceType.DIMENSION_CONTRIBUTION


def test_breakdown_tool_rejects_bad_dimension(registry, datasets):
    with pytest.raises(ValueError, match="whitelist"):
        registry.execute(
            "call-0",
            "breakdown_conversion_loss",
            ToolPolicy(),
            dataset_ref=datasets["normal"].path,
            dimension="user_id_hash",
        )


# --- analyze_benefit_gap -----------------------------------------------------------


def test_benefit_tool_friction_evidence(registry, datasets):
    res = registry.execute(
        "call-0", "analyze_benefit_gap", ToolPolicy(), dataset_ref=datasets["benefit_friction"].path
    )
    assert len(res.evidence) == 1
    ev = res.evidence[0]
    assert ev.evidence_type == EvidenceType.BENEFIT_GAP_FRICTION
    assert ev.metrics["mean_gap_shift_minor"] > 500
    # Plan § 13.3: must carry the not-sole-causal-proof warning.
    assert any("not sole causal proof" in w for w in res.warnings)


def test_benefit_tool_normal_no_evidence(registry, datasets):
    res = registry.execute(
        "call-0", "analyze_benefit_gap", ToolPolicy(), dataset_ref=datasets["normal"].path
    )
    assert res.evidence == []


# --- inspect_payment_events ---------------------------------------------------------


def test_inspect_tool_timeout_evidence(registry, datasets):
    res = registry.execute(
        "call-0",
        "inspect_payment_events",
        ToolPolicy(),
        dataset_ref=datasets["channel_timeout"].path,
    )
    types = {e.evidence_type for e in res.evidence}
    assert EvidenceType.CHANNEL_TIMEOUT in types
    ev = next(e for e in res.evidence if e.evidence_type == EvidenceType.CHANNEL_TIMEOUT)
    assert ev.metrics["timeout_count"] > 0
    assert "channel_b" in ev.dimensions["payment_channel"]


def test_inspect_tool_normal_no_timeout_evidence(registry, datasets):
    res = registry.execute(
        "call-0", "inspect_payment_events", ToolPolicy(), dataset_ref=datasets["normal"].path
    )
    assert EvidenceType.CHANNEL_TIMEOUT not in {e.evidence_type for e in res.evidence}


# --- mixed_failure: dual evidence (M1 acceptance) -------------------------------------


def test_mixed_failure_produces_benefit_and_timeout_evidence(registry, datasets):
    """M1 acceptance: mixed_failure must yield benefit-friction AND channel-timeout evidence."""
    policy = ToolPolicy()
    ledger = EvidenceLedger()
    path = datasets["mixed_failure"].path

    r1 = registry.execute("c1", "analyze_benefit_gap", policy, dataset_ref=path)
    r2 = registry.execute("c2", "inspect_payment_events", policy, dataset_ref=path)
    r3 = registry.execute("c3", "get_payment_funnel", policy, dataset_ref=path)
    for r in (r1, r2, r3):
        ledger.record_result(r)

    types = {e.evidence_type for e in ledger.all()}
    assert EvidenceType.BENEFIT_GAP_FRICTION in types
    assert EvidenceType.CHANNEL_TIMEOUT in types
    assert EvidenceType.FUNNEL_STAGE_DEGRADATION in types
