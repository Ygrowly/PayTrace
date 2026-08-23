"""Run deterministic B0 evaluations across multiple seeds.

This produces distribution statistics instead of relying on one favourable
seed. It does not use the database or call an external model.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import fmean, pstdev

from app.evaluation.models import EvaluationReport
from app.evaluation.runner import run_evaluation
from app.harness.artifact_store import LocalArtifactStore
from app.harness.scenarios.ground_truth import SCENARIO_KINDS

_METRIC_FIELDS = (
    "run_success_rate",
    "stage_localization_exact_rate",
    "stage_localization_overlap_mean",
    "root_cause_precision_mean",
    "root_cause_recall_mean",
    "root_cause_f1_mean",
    "evidence_validity_rate_mean",
    "unsupported_claim_rate_mean",
    "loss_attribution_mae",
    "tool_call_count_mean",
    "latency_ms_mean",
    "badcase_count",
    "model_invocation_count",
    "fallback_count",
    "total_input_tokens",
    "total_output_tokens",
)


def _parse_csv_ints(value: str) -> list[int]:
    try:
        values = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("seeds must be comma-separated integers") from exc
    if not values:
        raise argparse.ArgumentTypeError("at least one seed is required")
    return list(dict.fromkeys(values))


def _parse_csv_strings(value: str) -> list[str]:
    values = [item.strip() for item in value.split(",") if item.strip()]
    invalid = sorted(set(values) - set(SCENARIO_KINDS))
    if not values:
        raise argparse.ArgumentTypeError("at least one scenario is required")
    if invalid:
        raise argparse.ArgumentTypeError(f"unsupported scenarios: {', '.join(invalid)}")
    return list(dict.fromkeys(values))


def summarize_reports(reports: list[EvaluationReport]) -> dict:
    """Aggregate per-seed reports into distribution and badcase statistics."""
    if not reports:
        raise ValueError("reports must not be empty")

    distributions: dict[str, dict[str, float | int]] = {}
    for field in _METRIC_FIELDS:
        values = [
            float(value)
            for report in reports
            if (value := getattr(report.metrics, field)) is not None
        ]
        if not values:
            continue
        distributions[field] = {
            "count": len(values),
            "mean": fmean(values),
            "stddev": pstdev(values),
            "min": min(values),
            "max": max(values),
        }

    badcase_categories: Counter[str] = Counter()
    badcase_scenarios: Counter[str] = Counter()
    for report in reports:
        for item in report.badcases:
            badcase_scenarios[str(item["scenario_kind"])] += 1
            badcase_categories.update(str(category) for category in item["categories"])

    return {
        "model_mode": "B0",
        "seeds": [report.seed for report in reports],
        "seed_count": len(reports),
        "num_intents": reports[0].num_intents,
        "scenario_kinds": [item.scenario_kind for item in reports[0].scenario_results],
        "metrics": distributions,
        "badcase_categories": dict(sorted(badcase_categories.items())),
        "badcase_scenarios": dict(sorted(badcase_scenarios.items())),
        "generator_version": reports[0].generator_version,
        "ontology_version": reports[0].ontology_version,
    }


def render_markdown(summary: dict) -> str:
    lines = [
        "# PayTrace Multi-seed B0 Evaluation",
        "",
        f"- Seeds: `{', '.join(str(seed) for seed in summary['seeds'])}`",
        f"- Intents per scenario: `{summary['num_intents']}`",
        f"- Scenarios: `{', '.join(summary['scenario_kinds'])}`",
        "",
        "## Metric distributions",
        "",
        "| Metric | Mean | Stddev | Min | Max |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, values in summary["metrics"].items():
        lines.append(
            f"| `{name}` | {values['mean']:.4f} | {values['stddev']:.4f} "
            f"| {values['min']:.4f} | {values['max']:.4f} |"
        )
    lines.extend(["", "## Badcases", ""])
    if summary["badcase_categories"]:
        for category, count in summary["badcase_categories"].items():
            lines.append(f"- `{category}`: {count}")
    else:
        lines.append("- No badcases across the evaluated seed matrix.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a multi-seed PayTrace B0 evaluation.")
    parser.add_argument("--out", type=Path, default=Path("data/evaluations/matrix"))
    parser.add_argument("--seeds", type=_parse_csv_ints, default=[11, 42, 73])
    parser.add_argument("--scenarios", type=_parse_csv_strings, default=list(SCENARIO_KINDS))
    parser.add_argument("--intents", type=int, default=500)
    args = parser.parse_args()

    reports: list[EvaluationReport] = []
    for seed in args.seeds:
        run_root = args.out / "runs" / f"seed-{seed}"
        execution = run_evaluation(
            evaluation_run_id=f"matrix-b0-{seed}",
            model_mode="B0",
            scenario_kinds=args.scenarios,
            seed=seed,
            num_intents=args.intents,
            scenario_root=run_root / "scenarios",
            artifacts=LocalArtifactStore(run_root / "artifacts"),
        )
        run_root.mkdir(parents=True, exist_ok=True)
        (run_root / "report.json").write_bytes(execution.json_bytes)
        (run_root / "report.md").write_bytes(execution.markdown_bytes)
        reports.append(execution.report)

    summary = summarize_reports(reports)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "matrix.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.out / "matrix.md").write_text(render_markdown(summary), encoding="utf-8")
    print(
        f"seeds={summary['seed_count']} scenarios={len(summary['scenario_kinds'])} "
        f"root_cause_f1_mean={summary['metrics']['root_cause_f1_mean']['mean']:.4f}"
    )
    print(f"JSON: {args.out / 'matrix.json'}")
    print(f"Markdown: {args.out / 'matrix.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
