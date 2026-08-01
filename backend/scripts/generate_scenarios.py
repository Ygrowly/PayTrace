"""CLI: generate all 5 scenario datasets + ground truth files.

Usage:
    uv run python scripts/generate_scenarios.py [--out DIR] [--seed N] [--intents N]

Outputs (under --out, default ``data/scenarios``):
    <out>/events/<scenario_id>.parquet            runtime event datasets
    <out>/ground_truth/<scenario_id>.ground_truth.json

Ground Truth is written by ``GroundTruthLoader`` into a separate directory
tree; nothing in the events output references it.
"""

import argparse
import sys
from pathlib import Path

from app.harness.scenarios.generator import ScenarioConfig, generate_scenario
from app.harness.scenarios.ground_truth import SCENARIO_KINDS, GroundTruthLoader
from app.harness.scenarios.io import write_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PayTrace scenario datasets.")
    parser.add_argument("--out", type=Path, default=Path("data/scenarios"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--intents", type=int, default=5000)
    args = parser.parse_args()

    events_root = args.out / "events"
    gt_loader = GroundTruthLoader(args.out / "ground_truth")

    for kind in SCENARIO_KINDS:
        cfg = ScenarioConfig(kind=kind, seed=args.seed, num_intents=args.intents)
        events, gt = generate_scenario(cfg)
        ref = write_dataset(events, events_root, kind)
        gt_loader.save(gt)
        print(
            f"{kind:18s} events={ref.num_events:6d} "
            f"sha256={ref.checksum_sha256[:12]}... -> {ref.path}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
