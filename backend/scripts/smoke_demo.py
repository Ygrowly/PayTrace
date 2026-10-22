"""Run a deterministic PayTrace API demo without a browser or paid model.

The target stack must already have PostgreSQL, Redis, MinIO, the API and a
Celery worker running. The script creates local demo data by design.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

JsonObject = dict[str, Any]
RequestJson = Callable[[str, str, JsonObject | None, dict[str, str] | None], JsonObject]

_SUCCESS_STATUSES = {"SUCCEEDED", "NEEDS_DATA"}
_FAILURE_STATUSES = {"FAILED", "CANCELLED", "DISPATCH_FAILED"}


class DemoError(RuntimeError):
    """Raised when the deterministic demo cannot complete."""


def _request_json(
    method: str,
    url: str,
    payload: JsonObject | None = None,
    headers: dict[str, str] | None = None,
) -> JsonObject:
    if urlsplit(url).scheme not in {"http", "https"}:
        raise DemoError(f"Only http/https API URLs are allowed: {url}")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Accept": "application/json", **(headers or {})}
    if data is not None:
        request_headers["Content-Type"] = "application/json"
    request = Request(  # noqa: S310 - scheme is restricted above
        url, data=data, headers=request_headers, method=method
    )
    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310 - caller controls API base
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise DemoError(f"HTTP {exc.code} from {url}: {detail[:500]}") from exc
    except URLError as exc:
        raise DemoError(f"API is unreachable at {url}: {exc.reason}") from exc
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise DemoError(f"Expected a JSON object from {url}")
    return parsed


def run_demo(
    *,
    api_base: str,
    scenario: str,
    seed: int,
    num_intents: int,
    timeout_seconds: float,
    poll_interval: float,
    request_json: RequestJson = _request_json,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> JsonObject:
    """Create and diagnose one simulated incident, returning a compact summary."""
    base = api_base.rstrip("/")
    incident = request_json(
        "POST",
        f"{base}/api/v1/incidents/simulated",
        {"scenario_kind": scenario, "seed": seed, "num_intents": num_intents},
        None,
    )
    incident_id = str(incident["id"])
    idempotency_key = f"smoke-demo-{incident_id}-{uuid.uuid4().hex[:12]}"
    trigger = request_json(
        "POST",
        f"{base}/api/v1/incidents/{incident_id}/diagnosis-runs",
        None,
        {"Idempotency-Key": idempotency_key},
    )
    run_id = str(trigger["diagnosis_run_id"])

    deadline = monotonic() + timeout_seconds
    status = str(trigger["status"])
    run: JsonObject = trigger
    while status not in _SUCCESS_STATUSES | _FAILURE_STATUSES:
        if monotonic() >= deadline:
            raise DemoError(f"Diagnosis {run_id} did not finish within {timeout_seconds:g}s")
        sleep(poll_interval)
        run = request_json("GET", f"{base}/api/v1/diagnosis-runs/{run_id}", None, None)
        status = str(run["status"])

    if status in _FAILURE_STATUSES:
        error_type = run.get("error_type") or "UNKNOWN"
        error_message = run.get("error_message") or "no error message"
        raise DemoError(f"Diagnosis {run_id} ended as {status}: {error_type}: {error_message}")

    report = request_json("GET", f"{base}/api/v1/diagnosis-runs/{run_id}/report", None, None)
    trace = request_json("GET", f"{base}/api/v1/diagnosis-runs/{run_id}/trace", None, None)
    return {
        "incident_id": incident_id,
        "diagnosis_run_id": run_id,
        "status": status,
        "scenario": scenario,
        "seed": seed,
        "num_intents": num_intents,
        "summary": report.get("summary"),
        "root_causes": [item.get("label") for item in report.get("root_causes", [])],
        "tool_execution_count": len(trace.get("tool_executions", [])),
        "evidence_count": len(trace.get("evidence", [])),
        "total_duration_ms": run.get("total_duration_ms"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a deterministic PayTrace API smoke demo.")
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--scenario", default="mixed_failure")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--intents", type=int, default=500)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--poll-interval", type=float, default=1)
    args = parser.parse_args()
    try:
        result = run_demo(
            api_base=args.api_base,
            scenario=args.scenario,
            seed=args.seed,
            num_intents=args.intents,
            timeout_seconds=args.timeout,
            poll_interval=args.poll_interval,
        )
    except (DemoError, KeyError, json.JSONDecodeError) as exc:
        print(f"demo failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
