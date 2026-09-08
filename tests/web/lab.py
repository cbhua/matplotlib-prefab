"""Drive the published tool in a real browser, from Python.

Every browser-side verification in this project goes through here so that they
are all talking to the *same* page a person would open — not to a stripped-down
harness that could pass while the tool itself is broken.

The tool exposes ``window.__labApi`` for exactly this. It is a read/command
surface over the app's own state, not a second implementation: ``renderOnce``
posts to the same worker the sliders post to, and the profile it hands back is
the one the panel is editing.
"""

from __future__ import annotations

import contextlib
import os
import sys
from typing import Any, Dict, List, Optional

TESTS_WEB = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TESTS_WEB))
if TESTS_WEB not in sys.path:
    sys.path.insert(0, TESTS_WEB)

from server import static_server  # noqa: E402

BOOT_TIMEOUT_MS = 240_000


class Lab:
    """One browser, one loaded page, for the life of a ``with`` block."""

    def __init__(self, page, origin: str, browser_version: str) -> None:
        self.page = page
        self.origin = origin
        self.browser_version = browser_version
        self.console: List[str] = []
        self.page_errors: List[str] = []

    # -- lifecycle ---------------------------------------------------------

    def wait_ready(self, timeout: int = BOOT_TIMEOUT_MS) -> Dict[str, Any]:
        self.page.wait_for_function(
            "window.__labApi && (window.__labApi.ready() || window.__labApi.bootError())",
            timeout=timeout,
        )
        error = self.page.evaluate("window.__labApi.bootError()")
        if error:
            raise RuntimeError("the runtime failed to start in the browser: %s" % error)
        return self.page.evaluate("window.__lab.environment")

    def wait_for_render(self, timeout: int = 120_000) -> Dict[str, Any]:
        """Block until the tool is idle and showing the configuration on screen.

        Idle, not merely "a render finished": the tool debounces, so a request
        that has not fired yet would land in the middle of an assertion and put
        the page back into its working state. Waiting on the signature as well
        means a result for a superseded configuration is never mistaken for this
        one.
        """
        self.page.wait_for_function("() => window.__labApi.idle()", timeout=timeout)
        return self.page.evaluate("window.__labApi.lastGood()")

    # -- commands ----------------------------------------------------------

    def render_once(self, spec: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
        return self.page.evaluate(
            "async ([spec, profile]) => window.__labApi.renderOnce(spec, profile)",
            [spec, profile],
        )

    def select(self, venue: str, layout: str) -> Dict[str, Any]:
        return self.page.evaluate(
            "async ([v, l]) => window.__labApi.select(v, l)", [venue, layout]
        )

    def set_control(self, path: str, value: Any) -> None:
        self.page.evaluate("([p, v]) => window.__labApi.setControl(p, v)", [path, value])

    def reset_all(self) -> None:
        self.page.evaluate("() => window.__labApi.resetAll()")

    def controls(self) -> List[Dict[str, Any]]:
        return self.page.evaluate("() => window.__labApi.controls()")

    def profile(self) -> Dict[str, Any]:
        return self.page.evaluate("() => window.__labApi.currentProfile()")

    def spec(self) -> Dict[str, Any]:
        return self.page.evaluate("() => window.__labApi.currentSpec()")

    def page_manifest(self) -> Dict[str, Any]:
        return self.page.evaluate("() => window.__labApi.currentPage()")

    def export_bundle(self) -> Dict[str, Any]:
        return self.page.evaluate("() => window.__labApi.exportBundle()")

    def export_text(self) -> str:
        return self.page.evaluate("() => window.__labApi.exportText()")

    def status(self) -> Dict[str, str]:
        return {
            "kind": self.page.get_attribute("#status", "data-kind"),
            "text": self.page.inner_text("#status"),
        }

    def export_ready(self) -> bool:
        return self.page.get_attribute("#export-state", "data-ready") == "true"

    def javascript_heap_bytes(self) -> Optional[int]:
        return self.page.evaluate(
            "() => (performance.memory ? performance.memory.usedJSHeapSize : null)"
        )


@contextlib.contextmanager
def open_lab(headless: bool = True, viewport=(1500, 1000), device_scale_factor: float = 1.0):
    """Serve ``web/`` and open the tool in headless Chromium.

    ``device_scale_factor`` is what makes a screenshot comparable with a raster
    of a PDF: at 1.0 the page is captured in CSS pixels (96 per inch), so a
    comparison against a 300 DPI raster would be comparing two different
    resolutions. Callers that screenshot for measurement pass 300/96.
    """
    from playwright.sync_api import sync_playwright

    with static_server(os.path.join(REPO_ROOT, "web")) as origin:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={"width": viewport[0], "height": viewport[1]},
                device_scale_factor=device_scale_factor,
            )
            page = context.new_page()
            lab = Lab(page, origin, browser.version)
            page.on("console", lambda message: lab.console.append(
                "%s: %s" % (message.type, message.text)))
            page.on("pageerror", lambda error: lab.page_errors.append(str(error)))
            page.goto(origin + "/index.html")
            try:
                yield lab
            finally:
                context.close()
                browser.close()
