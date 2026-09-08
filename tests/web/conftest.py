"""Fixtures for the browser tests.

These tests need three things that are not part of an ordinary checkout: the
fetched Pyodide runtime, the packaged fonts, and a Playwright browser. Each is
checked for separately and skipped with a message that says exactly which
command produces it — a test that silently did not run is worse than one that
did not exist.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

TESTS_WEB = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TESTS_WEB))
GENERATED = os.path.join(REPO_ROOT, "web", "public", "generated")
CALIBRATION = os.path.join(TESTS_WEB, "calibration")

for path in (TESTS_WEB, os.path.join(REPO_ROOT, "scripts"),
             os.path.join(REPO_ROOT, "skills", "scientific-figures", "scripts")):
    if path not in sys.path:
        sys.path.insert(0, path)


def missing_runtime() -> str:
    lock = os.path.join(REPO_ROOT, "web", "pyodide.lock.json")
    if not os.path.isfile(lock):
        return "web/pyodide.lock.json is missing"
    with open(lock, encoding="utf-8") as handle:
        entries = json.load(handle)["files"]
    directory = os.path.join(GENERATED, "pyodide")
    absent = [entry["name"] for entry in entries
              if not os.path.isfile(os.path.join(directory, entry["name"]))]
    return "%d runtime file(s) not fetched" % len(absent) if absent else ""


def have_playwright() -> bool:
    import importlib.util

    return importlib.util.find_spec("playwright.sync_api") is not None


needs_runtime = pytest.mark.skipif(
    bool(missing_runtime()),
    reason="the browser runtime is not on disk (%s); run `python scripts/fetch_pyodide.py`"
           % (missing_runtime() or "ok"),
)

needs_fonts = pytest.mark.skipif(
    not os.path.isfile(os.path.join(GENERATED, "fonts", "fonts.json")),
    reason="the web fonts are not packaged; run `python scripts/build_fonts.py`",
)

needs_browser = pytest.mark.skipif(
    not have_playwright(),
    reason="playwright is not installed; `pip install playwright && playwright install chromium`",
)


def load_report(*parts):
    path = os.path.join(CALIBRATION, *parts)
    if not os.path.isfile(path):
        pytest.skip("%s has not been generated; see tests/web/README.md"
                    % os.path.relpath(path, REPO_ROOT))
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="session")
def lab():
    """One browser session shared by every test that needs the live tool.

    Starting Pyodide costs a couple of seconds; doing it per test would make the
    suite slow enough that people stop running it, which is its own failure mode.
    Tests that mutate the tool's state reset it themselves.
    """
    from lab import open_lab

    with open_lab() as session:
        session.wait_ready()
        session.wait_for_render()
        yield session
