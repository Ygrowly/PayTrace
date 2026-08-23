"""Tests for multi-seed evaluation aggregation."""

import pytest

from app.evaluation.models import AggregateMetrics, EvaluationReport, ScenarioResult
from scripts.evaluate_matrix import (
    _parse_csv_ints,
    _parse_csv_strings,
    render_markdown,
    summarize_reports,
)


def _report(seed: int, f1: float, badcases: list[dict] | None = None) -> EvaluationReport:
    return EvaluationReport(
        evaluation_run_id=f"run-{seed}",
        model_mode="B0",
        seed=seed,
        num_intents=100,
        metrics=AggregateMetrics(
            scenario_count=1,
            succeeded_count=1,
            run_success_rate=1.0,
            stage_localization_exact_rate=0.5,
            stage_localization_overlap_mean=0.75,
            root_cause_precision_mean=f1,
            root_cause_recall_mean=f1,
            root_cause_f1_mean=f1,
            evidence_validity_rate_mean=1.0,
            unsupported_claim_rate_mean=0.0,
            loss_attribution_mae=None,
            tool_call_count_mean=6.0,
            latency_ms_mean=10.0,
            badcase_count=len(badcases or []),
        ),
        scenario_results=[
            ScenarioResult(
                scenario_kind="normal", scenario_id=f"normal-{seed}", diagnosis_status="SUCCEEDED"
            )
        ],
        badcases=badcases or [],
        generator_version="generator.v1",
        ontology_version="ontology.v1",
    )


def test_summarize_reports_exposes_distribution_and_badcases():
    reports = [
        _report(11, 0.8),
        _report(42, 1.0, [{"scenario_kind": "normal", "categories": ["STAGE_MISS"]}]),
    ]
    summary = summarize_reports(reports)
    assert summary["seeds"] == [11, 42]
    assert summary["metrics"]["root_cause_f1_mean"] == {
        "count": 2,
        "mean": 0.9,
        "stddev": pytest.approx(0.1),
        "min": 0.8,
        "max": 1.0,
    }
    assert "loss_attribution_mae" not in summary["metrics"]
    assert summary["badcase_categories"] == {"STAGE_MISS": 1}
    assert summary["badcase_scenarios"] == {"normal": 1}
    markdown = render_markdown(summary)
    assert "Metric distributions" in markdown
    assert "`STAGE_MISS`: 1" in markdown


def test_summarize_reports_rejects_empty_input():
    with pytest.raises(ValueError, match="must not be empty"):
        summarize_reports([])


def test_csv_parsers_validate_and_deduplicate():
    assert _parse_csv_ints("11,42,11") == [11, 42]
    assert _parse_csv_strings("normal,mixed_failure,normal") == ["normal", "mixed_failure"]
    with pytest.raises(Exception, match="comma-separated integers"):
        _parse_csv_ints("x")
    with pytest.raises(Exception, match="unsupported scenarios"):
        _parse_csv_strings("not-a-scenario")
