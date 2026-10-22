"""Diagnostic Harness: routing, hook-chain governance, ledger, and the loop.

These tests cover the claims the harness makes about itself: that it refuses
out-of-bounds calls, that it stops when more calls cannot change the conclusion,
and that a hypothesis its evidence rejected is not investigated again.
"""

import json

import pytest

from app.analytics.duckdb_source import DuckDBAnalyticsSource
from app.diagnosis.orchestrator import DiagnosisOrchestrator
from app.harness.harness import DiagnosticHarness
from app.harness.hooks import (
    ArtifactHook,
    Budget,
    BudgetHook,
    CapabilityBundleHook,
    IncidentScopeHook,
    RejectedHypothesisHook,
    SchemaValidationHook,
    ToolCallBlocked,
    ToolCallContext,
)
from app.harness.investigation import ScriptedInvestigationPolicy
from app.harness.ledger import (
    HypothesisLedger,
    HypothesisTerminal,
    evaluate_hypothesis,
    is_designated_probe,
)
from app.harness.routing import ALL_TOOLS, detect_signals, route_capabilities
from app.harness.scenarios.generator import (
    ScenarioConfig,
    generate_config_changes,
    generate_scenario,
)
from app.harness.scenarios.io import write_dataset
from app.ontology.registry import EvidenceType
from app.tools.base import ToolResult

# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_detect_signals_from_stages_and_data_quality():
    assert detect_signals(anomalous_stages=[]) == ["UNKNOWN"]
    assert detect_signals(anomalous_stages=["CHANNEL_SUCCEEDED"], missing_data=[]) == [
        "CHANNEL_TIMEOUT"
    ]
    assert detect_signals(anomalous_stages=["PAYMENT_INITIATED"], missing_data=[]) == [
        "DECISION_FRICTION"
    ]
    assert "DATA_INTEGRITY" in detect_signals(anomalous_stages=[], missing_data=["benefit_id"])


def test_route_unions_signals_and_always_allows_the_funnel():
    bundle = route_capabilities(
        anomalous_stages=["PAYMENT_INITIATED", "CHANNEL_SUCCEEDED"], missing_data=[]
    )
    assert set(bundle.signals) == {"DECISION_FRICTION", "CHANNEL_TIMEOUT"}
    assert bundle.allows("get_payment_funnel")
    assert bundle.allows("analyze_benefit_gap")
    assert bundle.allows("inspect_payment_events")


def test_unknown_signal_widens_rather_than_guesses():
    bundle = route_capabilities(anomalous_stages=[])
    assert bundle.allowed_tools == frozenset(ALL_TOOLS)


# ---------------------------------------------------------------------------
# Hook chain — write side blocks
# ---------------------------------------------------------------------------


def _ctx(tool: str, **arguments) -> ToolCallContext:
    return ToolCallContext(tool_name=tool, arguments=arguments, step=0)


def test_capability_bundle_blocks_a_tool_outside_the_bundle():
    bundle = route_capabilities(anomalous_stages=["CHANNEL_SUCCEEDED"])
    hook = CapabilityBundleHook(bundle)
    hook.check(_ctx("inspect_payment_events"))  # inside the bundle
    with pytest.raises(ToolCallBlocked) as exc:
        hook.check(_ctx("analyze_benefit_gap"))
    assert exc.value.code == "TOOL_NOT_IN_BUNDLE"


def test_incident_scope_blocks_a_foreign_dataset():
    hook = IncidentScopeHook("/data/incident-a.parquet")
    hook.check(_ctx("get_payment_funnel", dataset_ref="/data/incident-a.parquet"))
    with pytest.raises(ToolCallBlocked) as exc:
        hook.check(_ctx("get_payment_funnel", dataset_ref="/data/incident-b.parquet"))
    assert exc.value.code == "OUT_OF_INCIDENT_SCOPE"


def test_schema_hook_blocks_unknown_and_malformed_arguments():
    hook = SchemaValidationHook()
    hook.check(_ctx("breakdown_conversion_loss", dimension="payment_channel"))
    with pytest.raises(ToolCallBlocked) as unknown:
        hook.check(_ctx("breakdown_conversion_loss", dimension="payment_channel", limit=5))
    assert unknown.value.code == "SCHEMA_INVALID"

    with pytest.raises(ToolCallBlocked):
        hook.check(_ctx("breakdown_conversion_loss"))  # missing required dimension

    with pytest.raises(ToolCallBlocked):
        hook.check(_ctx("breakdown_conversion_loss", dimension="not_a_dimension"))


def test_budget_hook_blocks_once_the_budget_is_spent():
    budget = Budget(max_calls=1)
    hook = BudgetHook(budget)
    hook.check(_ctx("get_payment_funnel"))
    budget.consume()
    with pytest.raises(ToolCallBlocked) as exc:
        hook.check(_ctx("get_payment_funnel"))
    assert exc.value.code == "BUDGET_EXHAUSTED"


def test_rejected_hypothesis_cannot_be_re_investigated():
    ledger = HypothesisLedger()
    hypothesis = ledger.propose("CHANNEL_TIMEOUT", required_next_tool="inspect_payment_events")
    ledger.resolve(hypothesis.hypothesis_id, "REJECTED", reason="no timeout evidence")

    hook = RejectedHypothesisHook(ledger)
    with pytest.raises(ToolCallBlocked) as exc:
        hook.check(
            ToolCallContext(
                tool_name="inspect_payment_events",
                arguments={},
                step=1,
                hypothesis_id=hypothesis.hypothesis_id,
            )
        )
    assert exc.value.code == "HYPOTHESIS_REJECTED"


# ---------------------------------------------------------------------------
# Hook chain — read side degrades
# ---------------------------------------------------------------------------


def test_missing_artifact_degrades_instead_of_blocking():
    hook = ArtifactHook()
    result = ToolResult(
        tool_call_id="c0",
        tool_name="inspect_payment_events",
        status="success",
        summary="120 rows",
        artifact_ref=None,
        row_count=120,
    )
    hook.observe(_ctx("inspect_payment_events"), result)
    assert len(hook.degradations) == 1
    assert "without an artifact" in hook.degradations[0]


# ---------------------------------------------------------------------------
# Hypothesis ledger
# ---------------------------------------------------------------------------


def test_reproposing_a_rejected_hypothesis_needs_a_new_tool():
    ledger = HypothesisLedger()
    hypothesis = ledger.propose("CHANNEL_TIMEOUT", required_next_tool="inspect_payment_events")
    ledger.resolve(hypothesis.hypothesis_id, "REJECTED", reason="clean")

    # Same tool: refused.
    with pytest.raises(HypothesisTerminal):
        ledger.propose("CHANNEL_TIMEOUT", required_next_tool="inspect_payment_events")

    # A different tool is a genuinely different test.
    retested = ledger.propose("CHANNEL_TIMEOUT", required_next_tool="get_config_changes")
    assert retested.hypothesis_id == hypothesis.hypothesis_id


def test_terminal_hypothesis_cannot_be_reopened():
    ledger = HypothesisLedger()
    hypothesis = ledger.propose("CHANNEL_TIMEOUT")
    ledger.resolve(hypothesis.hypothesis_id, "SUPPORTED")
    with pytest.raises(HypothesisTerminal):
        ledger.start(hypothesis.hypothesis_id)


def test_only_a_designated_probe_can_settle_a_hypothesis():
    assert is_designated_probe("inspect_payment_events", "CHANNEL_TIMEOUT")
    assert not is_designated_probe("breakdown_conversion_loss", "CHANNEL_TIMEOUT")

    # An empty generic drilldown leaves the question open...
    assert evaluate_hypothesis("CHANNEL_TIMEOUT", set(), probe_completed=False) is None
    # ...but an empty dedicated probe rules it out.
    status, reason = evaluate_hypothesis("CHANNEL_TIMEOUT", set(), probe_completed=True)
    assert status == "REJECTED"
    assert reason


def test_observational_evidence_leaves_a_hypothesis_partial():
    """The ledger and the report must agree on how strong the same evidence is."""
    status, _ = evaluate_hypothesis(
        "BENEFIT_SELECTION_FRICTION",
        {EvidenceType.BENEFIT_GAP_FRICTION},
        probe_completed=True,
    )
    assert status == "PARTIAL"


# ---------------------------------------------------------------------------
# End-to-end harness runs
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def source():
    return DuckDBAnalyticsSource()


@pytest.fixture(scope="module")
def datasets(tmp_path_factory):
    root = tmp_path_factory.mktemp("harness-datasets")
    refs = {}
    for kind in (
        "normal",
        "benefit_friction",
        "channel_timeout",
        "mixed_failure",
        "data_gap",
        "adversarial_noise",
    ):
        events, _ = generate_scenario(ScenarioConfig(kind=kind, seed=42, num_intents=400))
        refs[kind] = write_dataset(events, root, kind)
        (root / f"{kind}.config_changes.json").write_text(
            json.dumps(generate_config_changes(kind, seed=42)), encoding="utf-8"
        )
    return refs


def _run(source, datasets, kind: str):
    harness = DiagnosticHarness(source=source, policy=ScriptedInvestigationPolicy())
    return harness.run(str(datasets[kind].path), incident_id="inc-1", diagnosis_run_id="run-1")


def test_clean_incident_stops_after_triage(source, datasets):
    """No localized stage and no data gap: further calls cannot change anything."""
    result = _run(source, datasets, "normal")
    assert len(result.tool_results) == 1
    assert result.blocked_calls == []


def test_channel_timeout_early_exits_once_the_hypothesis_is_settled(source, datasets):
    result = _run(source, datasets, "channel_timeout")
    ids = {r.tool_name for r in result.tool_results}
    assert "inspect_payment_events" in ids
    assert result.early_exit_reason == "ALL_HYPOTHESES_RESOLVED"
    assert len(result.tool_results) < 7, "early exit must beat the fixed pipeline"
    statuses = {h.root_cause_type: h.status for h in result.hypotheses}
    assert statuses["CHANNEL_TIMEOUT"] == "SUPPORTED"


def test_mixed_failure_resolves_both_hypotheses(source, datasets):
    result = _run(source, datasets, "mixed_failure")
    statuses = {h.root_cause_type: h.status for h in result.hypotheses}
    assert statuses["CHANNEL_TIMEOUT"] == "SUPPORTED"
    assert statuses["BENEFIT_SELECTION_FRICTION"] == "PARTIAL"


def test_hypotheses_left_open_are_closed_as_needs_data(source, datasets):
    result = _run(source, datasets, "data_gap")
    assert result.hypotheses
    assert all(h.status != "PROPOSED" for h in result.hypotheses)
    assert all(h.status != "INVESTIGATING" for h in result.hypotheses)


def test_bundle_restricts_the_tools_a_run_may_touch(source, datasets):
    result = _run(source, datasets, "channel_timeout")
    used = {r.tool_name for r in result.tool_results}
    assert used <= set(result.bundle.allowed_tools)


# ---------------------------------------------------------------------------
# Orchestrator integration
# ---------------------------------------------------------------------------


def test_orchestrator_b2_reports_the_same_claim_as_its_ledger(source, datasets):
    orchestrator = DiagnosisOrchestrator(source=source, agent_mode="B2")
    execution = orchestrator.run_detailed(
        str(datasets["channel_timeout"].path), scenario_id="channel_timeout"
    )
    assert execution.agent_mode == "B2"
    assert execution.report.status == "SUCCEEDED"

    claim = next(rc for rc in execution.report.root_causes if rc.label == "CHANNEL_TIMEOUT")
    hypothesis = next(h for h in execution.hypotheses if h.root_cause_type == "CHANNEL_TIMEOUT")
    assert claim.support_status == hypothesis.status


def test_orchestrator_b0_stays_the_fixed_pipeline(source, datasets):
    orchestrator = DiagnosisOrchestrator(source=source, agent_mode="B0")
    execution = orchestrator.run_detailed(
        str(datasets["channel_timeout"].path), scenario_id="channel_timeout"
    )
    assert execution.agent_mode == "B0"
    assert execution.hypotheses == ()
    assert execution.capability_bundle == {}
