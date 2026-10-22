"""Manual dev probe: check UI behaviour that a static screenshot cannot show.

Two checks, both driven through a real headless Chrome over DevTools Protocol:

1. **Trace rail** — selecting one figure must light the same chain in every
   panel and dim the rest. Verified by clicking and counting, because the whole
   point of the interaction happens after the click.
2. **Horizontal overflow** (``--viewport 390``) — nothing may exceed the
   viewport width unless it scrolls inside its own container.

Usage (with the web app running):

    cd backend
    uv run python scripts/trace_rail_probe.py ../logs/shots \
        http://localhost:3000/incidents/<id>
    uv run python scripts/trace_rail_probe.py ../logs/shots \
        http://localhost:3000/incidents/<id> --viewport 390

Writes ``trace-before.png`` / ``trace-after.png`` (or ``overflow.png``) into the
given directory, and exits non-zero when a check fails — usable as a manual gate
before a demo.

Not part of the test suite: it needs a browser and a live stack.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets

# A locally installed Chromium (playwright's cache is the usual source). Override
# with PAYTRACE_CHROME if yours lives elsewhere.
DEFAULT_CHROME = (
    r"C:\Users\Lenovo\AppData\Local\ms-playwright\chromium-1208\chrome-win64\chrome.exe"
)
CHROME = os.environ.get("PAYTRACE_CHROME", DEFAULT_CHROME)
DEBUG_PORT = 9222


class CDPClient:
    """Minimal DevTools Protocol client — just enough to navigate and evaluate."""

    def __init__(self, socket) -> None:  # noqa: ANN001 - websockets client
        self._socket = socket
        self._next_id = 0

    async def call(self, method: str, **params):  # noqa: ANN201
        self._next_id += 1
        message_id = self._next_id
        await self._socket.send(json.dumps({"id": message_id, "method": method, "params": params}))
        while True:
            reply = json.loads(await self._socket.recv())
            if reply.get("id") == message_id:
                if "error" in reply:
                    raise RuntimeError(f"{method}: {reply['error']}")
                return reply.get("result", {})

    async def evaluate(self, expression: str):  # noqa: ANN201
        result = await self.call(
            "Runtime.evaluate",
            expression=expression,
            returnByValue=True,
            awaitPromise=True,
        )
        return result.get("result", {}).get("value")

    async def screenshot(self, path: Path) -> None:
        data = (
            await self.call("Page.captureScreenshot", format="png", captureBeyondViewport=True)
        )["data"]
        path.write_bytes(base64.b64decode(data))
        print(f"  wrote {path}")


def wait_for_devtools(timeout: float = 20.0) -> str:
    """Poll the DevTools endpoint until a page target appears."""
    deadline = time.time() + timeout
    last_error = "no attempt made"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(  # noqa: S310 - localhost, fixed scheme
                f"http://127.0.0.1:{DEBUG_PORT}/json/list"
            ) as response:
                targets = json.load(response)
            for target in targets:
                if target.get("type") == "page":
                    return target["webSocketDebuggerUrl"]
        except OSError as exc:  # browser still starting up
            last_error = str(exc)
        time.sleep(0.4)
    raise RuntimeError(f"DevTools endpoint never came up: {last_error}")


SELECT_CHAIN = """
(() => {
  const buttons = Array.from(document.querySelectorAll('button[aria-pressed]'));
  const target = buttons.find((b) => b.textContent.includes('CHANNEL TIMEOUT'));
  if (!target) return 'not-found';
  target.click();
  return target.textContent.trim().slice(0, 40);
})()
"""

COUNTS = """
({
  pressed: document.querySelectorAll('[aria-pressed="true"]').length,
  dimmed: document.querySelectorAll('.opacity-25').length,
})
"""

# Elements wider than the viewport that are NOT inside a scroll container.
# Scrollers are how a dense table is meant to behave on a narrow screen;
# anything else overflowing means the page itself scrolls sideways.
OVERFLOW_CHECK = """
(() => {
  const de = document.documentElement;
  const vw = de.clientWidth;
  const inScroller = (el) => {
    let node = el.parentElement;
    while (node && node !== document.body) {
      const overflowX = getComputedStyle(node).overflowX;
      if (overflowX === 'auto' || overflowX === 'scroll') return true;
      node = node.parentElement;
    }
    return false;
  };
  const offenders = [];
  for (const el of document.querySelectorAll('body *')) {
    const rect = el.getBoundingClientRect();
    if (rect.right > vw + 1 && !inScroller(el)) {
      offenders.push({
        tag: el.tagName.toLowerCase(),
        cls: (el.className || '').toString().slice(0, 70),
        right: Math.round(rect.right),
      });
    }
  }
  return {
    vw: vw,
    scrollWidth: de.scrollWidth,
    overflow: de.scrollWidth - vw,
    offenders: offenders.slice(0, 8),
  };
})()
"""


def launch_browser() -> subprocess.Popen:
    """Start a headless Chromium with the DevTools endpoint open.

    Deliberately synchronous and outside the event loop: blocking subprocess
    creation does not belong in a coroutine (ASYNC220).
    """
    return subprocess.Popen(  # noqa: S603 - fixed local path, no shell
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-extensions",
            "--hide-scrollbars",
            f"--remote-debugging-port={DEBUG_PORT}",
            "--window-size=1440,1200",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


async def check_overflow(client: CDPClient, out: Path) -> int:
    layout = await client.evaluate(OVERFLOW_CHECK)
    print(f"viewport {layout['vw']}px: {layout}")
    await client.screenshot(out / "overflow.png")
    if layout["offenders"]:
        print("FAIL: content overflows the viewport without scrolling")
        return 1
    print("OK: nothing overflows outside a scroll container")
    return 0


async def check_trace_rail(client: CDPClient, out: Path) -> int:
    before = await client.evaluate(COUNTS)
    print(f"before click: {before}")
    await client.screenshot(out / "trace-before.png")

    clicked = await client.evaluate(SELECT_CHAIN)
    print(f"clicked: {clicked!r}")
    await asyncio.sleep(1.2)

    after = await client.evaluate(COUNTS)
    print(f"after click:  {after}")
    await client.screenshot(out / "trace-after.png")

    if clicked == "not-found":
        print("FAIL: nothing on the page carried a trace target")
        return 1
    if after["pressed"] != 1:
        print("FAIL: the selection is not a single exclusive target")
        return 1
    if after["dimmed"] == 0:
        print("FAIL: the rest of the page was not dimmed")
        return 1
    print("OK: one selection, unrelated panels dimmed")
    return 0


async def drive(url: str, out: Path, viewport: int | None) -> int:
    out.mkdir(parents=True, exist_ok=True)
    try:
        async with websockets.connect(wait_for_devtools(), max_size=80 * 1024 * 1024) as socket:
            client = CDPClient(socket)
            await client.call("Page.enable")
            await client.call("Runtime.enable")
            if viewport is not None:
                await client.call(
                    "Emulation.setDeviceMetricsOverride",
                    width=viewport,
                    height=844,
                    deviceScaleFactor=2,
                    mobile=viewport < 700,
                )
            await client.call("Page.navigate", url=url)
            await asyncio.sleep(7)  # let the client-side queries settle

            if viewport is not None:
                return await check_overflow(client, out)
            return await check_trace_rail(client, out)
    except OSError as exc:
        print(f"FAIL: could not reach the browser: {exc}")
        return 1


def main() -> int:
    args = [value for value in sys.argv[1:] if not value.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 2

    viewport: int | None = None
    if "--viewport" in sys.argv:
        index = sys.argv.index("--viewport")
        if index + 1 >= len(sys.argv):
            print("--viewport needs a width in pixels")
            return 2
        viewport = int(sys.argv[index + 1])

    chrome = launch_browser()
    try:
        return asyncio.run(drive(args[1], Path(args[0]), viewport))
    finally:
        chrome.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
