"""Run the deterministic M3 evaluation without a database or paid model call.

Usage:
    uv run python scripts/evaluate_rule_based.py --out data/evaluations
"""

import argparse
import sys
from pathlib import Path

from app.evaluation.runner import run_evaluation
from app.harness.artifact_store import LocalArtifactStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Run PayTrace Rule-based evaluation.")
    parser.add_argument("--out", type=Path, default=Path("data/evaluations"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--intents", type=int, default=5000)
    args = parser.parse_args()

    artifact_root = args.out / "artifacts"
    execution = run_evaluation(
        evaluation_run_id="cli-rule-based",
        seed=args.seed,
        num_intents=args.intents,
        scenario_root=Path("data/scenarios"),
        artifacts=LocalArtifactStore(artifact_root),
    )
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.json").write_bytes(execution.json_bytes)
    (args.out / "report.md").write_bytes(execution.markdown_bytes)
    print(
        f"scenarios={execution.report.metrics.scenario_count} "
        f"run_success_rate={execution.report.metrics.run_success_rate:.2%} "
        f"badcase_scenarios={execution.report.metrics.badcase_count}"
    )
    print(f"JSON: {args.out / 'report.json'}")
    print(f"Markdown: {args.out / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
