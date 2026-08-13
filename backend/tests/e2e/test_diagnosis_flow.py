"""E2E diagnosis flow: create incident -> trigger diagnosis -> verify report UI.

Setup uses the HTTP API directly (deterministic); browser-use only verifies
the UI rendering. The Celery worker runs the B0 rule-based adapter, so the
diagnosis outcome itself is deterministic (normal scenario -> SUCCEEDED with
NORMAL_PAYMENT_FAILURE).
"""

from __future__ import annotations

import time

import httpx
import pytest

from tests.e2e.helpers import extract_json, run_agent

pytestmark = [pytest.mark.e2e]

_TERMINAL = {"SUCCEEDED", "NEEDS_DATA", "FAILED", "CANCELLED"}


@pytest.fixture
def diagnosed_incident(api_url: str) -> dict:
    """Create a simulated incident, trigger diagnosis, wait for terminal state.

    Requires the Celery worker to be running (make run-worker). Polls up to
    90 seconds for the diagnosis to finish.
    """
    with httpx.Client(base_url=api_url, timeout=30) as client:
        resp = client.post(
            "/api/v1/incidents/simulated",
            json={
                "scenario_kind": "normal",
                "seed": 42,
                "num_intents": 500,
                "title": "E2E flow smoke incident",
            },
        )
        resp.raise_for_status()
        incident = resp.json()

        resp = client.post(
            f"/api/v1/incidents/{incident['id']}/diagnosis-runs",
            headers={"Idempotency-Key": f"e2e-flow-{incident['id']}"},
        )
        resp.raise_for_status()
        run_ref = resp.json()

        run_state: dict = {}
        for _ in range(45):
            resp = client.get(f"/api/v1/diagnosis-runs/{run_ref['diagnosis_run_id']}")
            resp.raise_for_status()
            run_state = resp.json()
            if run_state["status"] in _TERMINAL:
                break
            time.sleep(2)

        return {"incident": incident, "run": run_state}


async def test_incident_detail_shows_diagnosis_report(
    e2e_browser, e2e_llm, web_url: str, diagnosed_incident: dict
) -> None:
    """The detail page renders the completed diagnosis report."""
    incident = diagnosed_incident["incident"]
    run_state = diagnosed_incident["run"]
    assert run_state["status"] == "SUCCEEDED", f"Diagnosis did not succeed: {run_state}"

    incident_id = incident["id"]
    task = (
        f"Go to {web_url}/incidents/{incident_id}. "
        "Return ONLY a JSON object with these keys, all booleans: "
        "'has_incident_title' (true if the page contains the text "
        "'E2E flow smoke incident'), "
        "'has_root_cause' (true if the page contains the text "
        "'Normal payment failure'), "
        "'has_succeeded' (true if the page contains the text 'SUCCEEDED'). "
        "Do not include any other keys or text."
    )
    result = await run_agent(task, e2e_browser, e2e_llm)
    data = extract_json(result)
    assert data is not None, f"Agent did not return JSON: {result!r}"
    assert (
        data.get("has_incident_title") is True
    ), f"Detail page did not show the incident title: {data}"
    assert (
        data.get("has_root_cause") is True
    ), f"Detail page did not show the root cause card: {data}"
    assert data.get("has_succeeded") is True, f"Detail page did not show run status: {data}"


async def test_incidents_list_shows_new_incident(
    e2e_browser, e2e_llm, web_url: str, diagnosed_incident: dict
) -> None:
    """The /incidents list shows the newly created incident."""
    task = (
        f"Go to {web_url}/incidents. "
        "Return ONLY a JSON object with one key "
        "'has_new_incident' (boolean: true if the page contains the text "
        "'E2E flow smoke incident'). "
        "Do not include any other keys or text."
    )
    result = await run_agent(task, e2e_browser, e2e_llm)
    data = extract_json(result)
    assert data is not None, f"Agent did not return JSON: {result!r}"
    assert (
        data.get("has_new_incident") is True
    ), f"Incidents list did not show the new incident: {data}"
