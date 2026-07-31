"""Export the FastAPI OpenAPI document to a JSON file.

This script loads the FastAPI app *without* binding to a port, then persists
`app.openapi()` to disk. It is used:

* locally by developers updating the on-repo contract (`backend/openapi.json`),
* by CI to detect drift between the code and the on-repo contract.

Usage:
    uv run python scripts/export_openapi.py --out openapi.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make `app` importable when invoked as `python scripts/export_openapi.py` from
# `backend/`. Using relative path insertion keeps the script self-contained
# instead of requiring `pip install -e .` or `PYTHONPATH` manipulation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export FastAPI OpenAPI spec to JSON.")
    parser.add_argument(
        "--out",
        required=True,
        help="Output file path (e.g. openapi.json or /tmp/openapi.current.json).",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    spec = app.openapi()
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, sort_keys=False)
        f.write("\n")

    print(f"Exported OpenAPI spec to {out_path}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
