"""Ground Truth model and isolated loader (plan § 12.3).

Ground Truth is stored independently from runtime datasets. The diagnosis
process must use a separate loader and must NOT be able to read Ground Truth
from its code path — ``DatasetRef`` points only at runtime event data, never
at Ground Truth. Diagnosis answers must never be hard-coded from
``scenario_id`` or file names.
"""

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

GENERATOR_VERSION = "paytrace.scenariogen.v1"


class InjectedParameters(BaseModel):
    """Fault-injection knobs actually used for a scenario."""

    benefit_gap_shift_minor: int = 0
    high_gap_cancel_rate: float = 0.0
    high_gap_switch_rate: float = 0.0
    timeout_channel: str | None = None
    timeout_rate: float = 0.0
    timeout_latency_multiplier: float = 1.0
    drop_funnel_stages: list[str] = Field(default_factory=list)
    null_benefit_id_rate: float = 0.0


class GroundTruth(BaseModel):
    """Ground truth for one scenario (plan § 12.3 required fields)."""

    scenario_id: str
    expected_anomalous_stages: list[str]
    expected_root_causes: list[str]
    affected_dimensions: dict[str, list[str]]
    injected_parameters: InjectedParameters
    expected_data_gaps: list[str]
    generator_version: str = GENERATOR_VERSION
    random_seed: int
    created_at: datetime

    model_config = {"frozen": True}


class GroundTruthLoader:
    """Dedicated loader for Ground Truth files.

    Kept in a separate module from the diagnosis path so that diagnosis code
    never imports it. Storage layout: ``<root>/<scenario_id>.ground_truth.json``.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, scenario_id: str) -> Path:
        if "/" in scenario_id or "\\" in scenario_id or scenario_id in ("", ".", ".."):
            msg = f"invalid scenario_id: {scenario_id!r}"
            raise ValueError(msg)
        return Path(self._root) / f"{scenario_id}.ground_truth.json"

    def save(self, gt: GroundTruth) -> None:
        self._path_for(gt.scenario_id).write_text(gt.model_dump_json(indent=2), encoding="utf-8")

    def load(self, scenario_id: str) -> GroundTruth:
        return GroundTruth.model_validate_json(
            self._path_for(scenario_id).read_text(encoding="utf-8")
        )


ScenarioKind = Literal[
    "normal",
    "benefit_friction",
    "channel_timeout",
    "mixed_failure",
    "data_gap",
    "adversarial_irrelevant_config",
    "adversarial_noise",
]

SCENARIO_KINDS: list[ScenarioKind] = [
    "normal",
    "benefit_friction",
    "channel_timeout",
    "mixed_failure",
    "data_gap",
    "adversarial_irrelevant_config",
    "adversarial_noise",
]
