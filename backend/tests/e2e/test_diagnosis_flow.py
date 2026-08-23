"""E2E diagnosis flow: create incident -> trigger diagnosis -> verify report UI.

Setup uses the HTTP API directly (deterministic); browser-use only verifies
the UI rendering. The Celery worker runs the B0 rule-based adapter, so the
diagnosis outcome itself is deterministic (normal scenario -> SUCCEEDED with
NORMAL_PAYMENT_FAILURE).
"""

from __future__ import annotations

import pytest

from tests.e2e.helpers import extract_json, run_agent

pytestmark = [pytest.mark.e2e, pytest.mark.llm_e2e]


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
