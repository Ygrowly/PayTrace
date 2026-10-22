"""Shared helpers for the browser-use E2E suite."""

from __future__ import annotations

import json
import re


async def run_agent(task: str, browser, llm) -> str:
    """Run a browser-use Agent and return its final result text."""
    from browser_use import Agent

    agent = Agent(task=task, llm=llm, browser=browser)
    history = await agent.run()
    return history.final_result() or ""


def extract_json(text: str) -> dict | None:
    """Best-effort extraction of a JSON object from LLM output."""
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
