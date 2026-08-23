"""Deterministic tests for the public API demo script."""

from collections.abc import Iterator

import pytest

from scripts.smoke_demo import DemoError, run_demo


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_run_demo_completes_and_summarises_trace():
    statuses: Iterator[dict] = iter(
        [
            {"status": "RUNNING"},
            {"status": "SUCCEEDED", "total_duration_ms": 125},
        ]
    )
    calls: list[tuple[str, str]] = []

    def request(method, url, payload, headers):  # noqa: ANN001, ANN202, ARG001
        calls.append((method, url))
        if url.endswith("/incidents/simulated"):
            assert payload == {"scenario_kind": "mixed_failure", "seed": 42, "num_intents": 50}
            return {"id": "incident-1"}
        if url.endswith("/diagnosis-runs"):
            assert headers and headers["Idempotency-Key"].startswith("smoke-demo-incident-1-")
            return {"diagnosis_run_id": "run-1", "status": "QUEUED"}
        if url.endswith("/diagnosis-runs/run-1"):
            return next(statuses)
        if url.endswith("/report"):
            return {"summary": "Two causes found", "root_causes": [{"label": "CAUSE_A"}]}
        if url.endswith("/trace"):
            return {"tool_executions": [{}, {}], "evidence": [{}, {}, {}]}
        raise AssertionError(f"unexpected request: {method} {url}")

    clock = FakeClock()
    result = run_demo(
        api_base="http://api.test/",
        scenario="mixed_failure",
        seed=42,
        num_intents=50,
        timeout_seconds=10,
        poll_interval=0.5,
        request_json=request,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )

    assert result["status"] == "SUCCEEDED"
    assert result["root_causes"] == ["CAUSE_A"]
    assert result["tool_execution_count"] == 2
    assert result["evidence_count"] == 3
    assert result["total_duration_ms"] == 125
    assert calls[-2:] == [
        ("GET", "http://api.test/api/v1/diagnosis-runs/run-1/report"),
        ("GET", "http://api.test/api/v1/diagnosis-runs/run-1/trace"),
    ]


def test_run_demo_surfaces_terminal_failure():
    def request(method, url, payload, headers):  # noqa: ANN001, ANN202, ARG001
        if url.endswith("/incidents/simulated"):
            return {"id": "incident-1"}
        if url.endswith("/diagnosis-runs"):
            return {"diagnosis_run_id": "run-1", "status": "QUEUED"}
        return {"status": "FAILED", "error_type": "BROKEN", "error_message": "worker failed"}

    clock = FakeClock()
    with pytest.raises(DemoError, match="BROKEN: worker failed"):
        run_demo(
            api_base="http://api.test",
            scenario="normal",
            seed=1,
            num_intents=10,
            timeout_seconds=5,
            poll_interval=0,
            request_json=request,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )


def test_run_demo_times_out():
    def request(method, url, payload, headers):  # noqa: ANN001, ANN202, ARG001
        if url.endswith("/incidents/simulated"):
            return {"id": "incident-1"}
        if url.endswith("/diagnosis-runs"):
            return {"diagnosis_run_id": "run-1", "status": "QUEUED"}
        return {"status": "RUNNING"}

    clock = FakeClock()
    with pytest.raises(DemoError, match="did not finish"):
        run_demo(
            api_base="http://api.test",
            scenario="normal",
            seed=1,
            num_intents=10,
            timeout_seconds=1,
            poll_interval=0.6,
            request_json=request,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )
