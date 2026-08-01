"""Scenario dataset persistence (plan § 12).

Runtime events are written to Parquet (one file per scenario) and described by
a ``DatasetRef``. ``DatasetRef`` points ONLY at runtime event data — Ground
Truth is stored separately via ``GroundTruthLoader`` and is never reachable
from a ``DatasetRef``, so the diagnosis path cannot read it.
"""

import hashlib
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel

from app.domain.events import CANONICAL_EVENT_COLUMNS, SCHEMA_VERSION, CanonicalPaymentEvent

DATASET_FORMAT_VERSION = "paytrace.dataset.v1"


class DatasetRef(BaseModel):
    """Pointer to a materialised runtime event dataset (never Ground Truth)."""

    scenario_id: str
    path: str
    format: str = "parquet"
    num_events: int
    checksum_sha256: str
    schema_version: str = SCHEMA_VERSION
    dataset_format_version: str = DATASET_FORMAT_VERSION

    model_config = {"frozen": True}


def _events_to_table(events: list[CanonicalPaymentEvent]) -> pa.Table:
    rows = [e.model_dump(mode="json") for e in events]
    columns: dict[str, list] = {
        name: [row[name] for row in rows] for name in CANONICAL_EVENT_COLUMNS
    }
    return pa.table(columns)


def write_dataset(events: list[CanonicalPaymentEvent], root: Path, scenario_id: str) -> DatasetRef:
    """Write events to ``<root>/<scenario_id>.parquet`` and return a DatasetRef."""
    if "/" in scenario_id or "\\" in scenario_id or scenario_id in ("", ".", ".."):
        msg = f"invalid scenario_id: {scenario_id!r}"
        raise ValueError(msg)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{scenario_id}.parquet"
    table = _events_to_table(events)
    pq.write_table(table, path)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    return DatasetRef(
        scenario_id=scenario_id,
        path=str(path),
        num_events=len(events),
        checksum_sha256=checksum,
    )


def read_dataset(ref: DatasetRef) -> list[CanonicalPaymentEvent]:
    """Load events back from a DatasetRef, verifying the file checksum."""
    path = Path(ref.path)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    if checksum != ref.checksum_sha256:
        msg = f"dataset checksum mismatch: {ref.path}"
        raise ValueError(msg)
    table = pq.read_table(path)
    rows = table.to_pylist()
    return [CanonicalPaymentEvent.model_validate(row) for row in rows]
