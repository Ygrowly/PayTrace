"""E2E smoke tests: verify the frontend workbench loads and renders key pages.

These are LLM-driven browser tests. Each test gives the Agent a narrow,
deterministic task ("visit URL, report X") and asserts on the returned
text. The Agent uses the project's MODEL_API_KEY (DeepSeek or any
OpenAI-compatible endpoint), so the suite is skipped unless that key
is configured and the stack is running.
"""

from __future__ import annotations

import json
import re

import pytest

pytestmark = [pytest.mark.e2e]


async def _run_agent(task: str, browser, llm) -> str:
    """Run a browser-use Agent and return its final result text."""
    from browser_use import Agent

    agent = Agent(task=task, llm=llm, browser=browser)
    history = await agent.run()
    return history.final_result() or ""


def _extract_json(text: str) -> dict | None:
    """Best-effort extraction of a JSON object from LLM output."""
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


async def test_homepage_loads(e2e_browser, e2e_llm, web_url) -> None:
    """The Next.js homepage renders and shows the backend health status."""
    task = (
        f"Go to {web_url}. "
        "Read the text displayed on the page. "
        "Return ONLY a JSON object with key 'page_text' "
        "(string: the exact text you see on the page)."
    )
    result = await _run_agent(task, e2e_browser, e2e_llm)
    data = _extract_json(result)
    assert data is not None, f"Agent did not return JSON: {result!r}"
    assert "ok" in str(data.get("page_text", "")).lower(), (
        f"Homepage did not show health ok: {data}"
    )


async def test_incidents_list_page_loads(e2e_browser, e2e_llm, web_url) -> None:
    """The /incidents page renders the incident list workbench."""
    task = (
        f"Go to {web_url}/incidents. "
        "Look at the rendered page. "
        "Return ONLY a JSON object with keys "
        "'title' (string: the page title or heading) and "
        "'has_create_button' (boolean: true if there is a button or link "
        "to create a new incident, e.g. 'Create', 'New incident', "
        "'Simulate', or similar). "
        "Return only the JSON, no other text."
    )
    result = await _run_agent(task, e2e_browser, e2e_llm)
    data = _extract_json(result)
    assert data is not None, f"Agent did not return JSON: {result!r}"
    assert (
        "incident" in (data.get("title") or "").lower() or data.get("has_create_button") is True
    ), f"Incidents page did not render as expected: {data}"


async def test_eval_lab_page_loads(e2e_browser, e2e_llm, web_url) -> None:
    """The /eval page renders the Eval Lab workbench."""
    task = (
        f"Go to {web_url}/eval. "
        "Look at the rendered page. "
        "Return ONLY a JSON object with keys "
        "'title' (string: the page title or heading) and "
        "'has_eval_content' (boolean: true if the page mentions "
        "'Evaluation', 'Eval', 'Run', or 'Badcase'). "
        "Return only the JSON, no other text."
    )
    result = await _run_agent(task, e2e_browser, e2e_llm)
    data = _extract_json(result)
    assert data is not None, f"Agent did not return JSON: {result!r}"
    assert data.get("has_eval_content") is True, f"Eval Lab page did not render as expected: {data}"
