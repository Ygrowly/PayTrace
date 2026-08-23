"""Deterministic browser checks for the public demo path.

These tests drive the real browser through browser-use's CDP runtime but never
instantiate an Agent or call a model. They are suitable for CI.
"""

from __future__ import annotations

import asyncio

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.deterministic_e2e]
_WAIT_ATTEMPTS = 120


async def _wait_for_body_text(browser, expected: str) -> str:
    page = await browser.get_current_page()
    assert page is not None, "browser did not expose the current page"

    text = ""
    for _ in range(_WAIT_ATTEMPTS):
        text = await page.evaluate("() => document.body?.innerText || ''")
        if expected.lower() in text.lower():
            return text
        await asyncio.sleep(0.25)
    raise AssertionError(f"{expected!r} not rendered; body={text[:1000]!r}")


async def _body_text(browser, url: str, expected: str) -> str:
    await browser.navigate_to(url)
    return await _wait_for_body_text(browser, expected)


async def test_public_workbench_pages_render(e2e_browser, web_url: str) -> None:
    home = await _body_text(e2e_browser, web_url, "Dependency readiness")
    assert "postgres" in home.lower()
    assert "redis" in home.lower()

    incidents = await _body_text(e2e_browser, f"{web_url}/incidents", "Incident workspace")
    assert "Create simulated incident" in incidents

    page = await e2e_browser.get_current_page()
    assert page is not None
    clicked = await page.evaluate(
        """() => {
          const button = [...document.querySelectorAll('button')]
            .find((item) => item.textContent?.includes('Create simulated incident'));
          button?.click();
          return Boolean(button);
        }"""
    )
    assert clicked.lower() == "true"
    await _wait_for_body_text(e2e_browser, "Harness")

    evaluation = await _body_text(e2e_browser, f"{web_url}/eval", "Eval Lab")
    assert "B0 · Rule based" in evaluation
    assert "B1 · Model backed" in evaluation


async def test_completed_diagnosis_renders_without_llm_browser_agent(
    e2e_browser, web_url: str, diagnosed_incident: dict
) -> None:
    run_state = diagnosed_incident["run"]
    assert run_state["status"] == "SUCCEEDED", f"Diagnosis did not succeed: {run_state}"

    incident_id = diagnosed_incident["incident"]["id"]
    body = await _body_text(
        e2e_browser,
        f"{web_url}/incidents/{incident_id}",
        "E2E flow smoke incident",
    )
    assert "normal payment failure" in body.lower()
    assert "succeeded" in body.lower()
