"""E2E fixtures: stack reachability gates, LLM, and browser-use Browser.

The suite is skipped wholesale unless all of these hold:
  - ``browser_use`` importable (installed via ``uv sync --extra e2e``)
  - API reachable at ``$E2E_API_URL`` (default http://localhost:8000)
  - Web reachable at ``$E2E_WEB_URL`` (default http://localhost:3000)
  - ``MODEL_API_KEY`` set in the environment (Agent is LLM-driven)

Gates run in an autouse fixture so the skip happens at test time, not
collection time — this keeps ``pytest --collect-only`` honest and avoids
importing browser_use when the gates fail.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

API_URL = os.getenv("E2E_API_URL", "http://localhost:8000")
WEB_URL = os.getenv("E2E_WEB_URL", "http://localhost:3000")

# Common Windows Chrome/Edge locations. browser-use's auto-detection can
# time out on Windows, so we pass an explicit executable_path when one is
# found. Override with E2E_CHROME_PATH env var if needed.
_CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _find_chrome() -> str | None:
    env_path = os.getenv("E2E_CHROME_PATH")
    if env_path and Path(env_path).exists():
        return env_path
    for candidate in _CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def _reachable(url: str, timeout: float = 2.0) -> bool:
    try:
        resp = httpx.get(url, timeout=timeout)
    except Exception:  # noqa: BLE001 — any failure means "not reachable"
        return False
    return resp.status_code < 400


def _check_gates() -> list[str]:
    """Return a list of failed gate reasons; empty list means all gates pass."""
    failures: list[str] = []
    try:
        import browser_use  # noqa: F401
    except ImportError:
        failures.append("browser-use not installed (run: uv sync --extra e2e)")

    if not os.getenv("MODEL_API_KEY"):
        failures.append("MODEL_API_KEY not set (E2E is LLM-driven)")

    if not _reachable(f"{API_URL}/api/v1/health/live"):
        failures.append(f"API not reachable at {API_URL} (run: make run-api)")

    if not _reachable(WEB_URL):
        failures.append(f"Web not reachable at {WEB_URL} (run: make run-web)")

    return failures


@pytest.fixture(autouse=True)
def _skip_if_gates_fail() -> None:
    """Skip every E2E test unless all prerequisites are satisfied."""
    failures = _check_gates()
    if failures:
        pytest.skip("E2E prerequisites not met: " + "; ".join(failures))


@pytest.fixture
def web_url() -> str:
    return WEB_URL


@pytest.fixture
def api_url() -> str:
    return API_URL


@pytest.fixture
def e2e_llm():
    """browser-use ChatOpenAI wired to the project's model settings.

    ``dont_force_structured_output`` is required for DeepSeek and other
    OpenAI-compatible endpoints that do not support ``response_format``;
    without it the agent fails with HTTP 400 on every LLM call.
    """
    from browser_use import ChatOpenAI

    from app.config import get_settings

    s = get_settings()
    return ChatOpenAI(
        model=s.model_name,
        api_key=s.model_api_key,
        base_url=s.model_base_url,
        temperature=0.0,
        max_retries=2,
        dont_force_structured_output=True,
    )


@pytest.fixture
async def e2e_browser():
    """Headless browser-use Browser, closed after the test.

    Passes an explicit Chrome executable_path on Windows because
    browser-use's auto-detection can time out. Also raises the browser
    start timeout to 60s for slow first-launch on Windows.
    """
    from browser_use import Browser

    kwargs: dict = {"headless": True}
    chrome_path = _find_chrome()
    if chrome_path:
        kwargs["executable_path"] = chrome_path
    browser = Browser(**kwargs)
    try:
        yield browser
    finally:
        try:
            await browser.close()
        except Exception:  # noqa: BLE001, S110 — cleanup must not fail the test
            pass
