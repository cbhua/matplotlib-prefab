#!/usr/bin/env python3
"""Phase A gate: does the repository's own drawing code run in a browser, and agree?

Before any UI is built on top of Pyodide, one question has to be answered with
measurements rather than with a plan: can ``figure_core`` and the templates —
the same files, not a port — load in a Web Worker, draw the ICML narrow case,
and produce the SVG the command line produces from the same spec and profile?

    python scripts/prototype_pyodide.py
    python scripts/prototype_pyodide.py --samples 50 --keep-svg

It starts a local server, drives headless Chromium through
``tests/web/harness/pyodide-prototype.html``, and writes a report to
``tests/web/calibration/pyodide-prototype.json``: cold-start bytes and time, hot
render times, the browser's package versions, and a structural comparison of the
browser SVG against a locally rendered one.

A mismatch is reported, never smoothed over. The comparison normalises nothing
except what is provably run-dependent (nothing, currently — the SVG is written
with a fixed id salt and no date), so a difference here is a real difference in
what the two environments draw.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from typing import Any, Dict, Optional, Sequence

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "skills", "scientific-figures", "scripts")
TESTS_WEB = os.path.join(REPO_ROOT, "tests", "web")
OUTPUT_DIR = os.path.join(TESTS_WEB, "calibration")
LOCK_PATH = os.path.join(REPO_ROOT, "web", "pyodide.lock.json")

for path in (SCRIPTS_DIR, TESTS_WEB, os.path.dirname(os.path.abspath(__file__))):
    if path not in sys.path:
        sys.path.insert(0, path)

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import figure_core  # noqa: E402
import parity  # noqa: E402
from server import static_server  # noqa: E402

# The ICML narrow case named in the plan: one column of the two-column body,
# 82.55 mm, as measured by the LaTeX probe in the committed context report.
ICML_COLUMN_MM = 82.55
DEFAULT_SPEC = os.path.join(REPO_ROOT, "tests", "data", "line-multi.json")
DEFAULT_PROFILE = os.path.join(
    REPO_ROOT, "skills", "scientific-figures", "references", "profiles", "single-column.json"
)


def case_inputs(spec_path: str, profile_path: str, width_mm: float):
    """The spec and the profile the comparison uses, on both sides."""
    import copy

    spec = figure_core.load_spec(spec_path)
    profile = copy.deepcopy(figure_core.load_profile(profile_path))
    profile["canvas"]["width_mm"] = width_mm
    return spec, profile


def local_svg(spec, profile) -> Dict[str, Any]:
    """The same render in the repository's own (newer) matplotlib."""
    started = time.perf_counter()
    result = figure_core.render_to_svg(spec, profile)
    result["local_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
    return result


def compare_svg(browser: str, local: str) -> Dict[str, Any]:
    """Structural comparison. Identical is identical; different says where."""
    if browser == local:
        return {"identical": True, "first_difference": None,
                "browser_bytes": len(browser), "local_bytes": len(local)}
    limit = min(len(browser), len(local))
    index = next((i for i in range(limit) if browser[i] != local[i]), limit)
    window = 90
    return {
        "identical": False,
        "first_difference": {
            "character_index": index,
            "browser": browser[max(0, index - window):index + window],
            "local": local[max(0, index - window):index + window],
        },
        "browser_bytes": len(browser),
        "local_bytes": len(local),
    }


def viewbox(svg: str) -> Optional[str]:
    import re

    match = re.search(r'viewBox="([^"]+)"', svg)
    return match.group(1) if match else None


def run(samples: int, width_mm: float, keep_svg: bool, timeout_s: int) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright

    with open(LOCK_PATH, encoding="utf-8") as handle:
        lock = json.load(handle)

    console: list = []
    page_errors: list = []
    transferred: Dict[str, int] = {}

    with static_server(REPO_ROOT) as origin:
        url = ("%s/tests/web/harness/pyodide-prototype.html?width_mm=%s&samples=%d"
               % (origin, width_mm, samples))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context()
            page = context.new_page()
            page.on("console", lambda msg: console.append("%s: %s" % (msg.type, msg.text)))
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            def on_response(response):
                try:
                    length = response.headers.get("content-length")
                    if length is not None:
                        transferred[response.url] = int(length)
                except Exception:
                    pass

            page.on("response", on_response)

            started = time.perf_counter()
            page.goto(url)
            page.wait_for_function("window.__done === true", timeout=timeout_s * 1000)
            wall = time.perf_counter() - started
            payload = page.evaluate("window.__result")
            browser_name = browser.version
            context.close()
            browser.close()

    hot = [entry["render_ms"] for entry in payload.get("renders", []) if entry.get("render_ms")]
    hot_wall = [entry["wall_ms"] for entry in payload.get("renders", []) if entry.get("wall_ms")]

    spec, profile = case_inputs(DEFAULT_SPEC, DEFAULT_PROFILE, width_mm)
    local = local_svg(spec, profile)
    browser_svg = payload.get("svg", "")
    comparison = compare_svg(browser_svg, local["svg"]) if browser_svg else None

    # The comparison that decides the gate is against the *pinned* interpreter:
    # the browser runs matplotlib %s, and a newer matplotlib drawing the same
    # figure slightly differently is a matplotlib change, not a browser problem.
    parity_result = None
    parity_comparison = None
    parity_error = None
    try:
        parity_result = parity.render_svg(spec, profile)
        parity_comparison = compare_svg(browser_svg, parity_result["svg"]) if browser_svg else None
    except parity.ParityError as exc:
        parity_error = str(exc)

    report: Dict[str, Any] = {
        "report_version": "1",
        "kind": "pyodide-prototype",
        "question": "Can this repository's figure_core draw in a browser worker, and does "
                    "the SVG match the command line's?",
        "case": {
            "spec": os.path.relpath(DEFAULT_SPEC, REPO_ROOT),
            "profile": os.path.relpath(DEFAULT_PROFILE, REPO_ROOT),
            "width_mm": width_mm,
            "width_source": "ICML 2026 \\columnwidth, measured by the LaTeX probe in "
                            "tests/output/conference-context/icml2026/line-multi/context-report.json",
        },
        "browser": {
            "engine": "chromium (playwright)",
            "version": browser_name,
            "headless": True,
        },
        "runtime": {
            "pyodide_version": lock["pyodide_version"],
            "self_hosted": True,
            "download_bytes": lock["total_bytes"],
            "download_mib": lock["total_mib"],
            "pinned_packages": lock["packages"],
            "reported_by_worker": payload.get("environment"),
        },
        "local": {
            "repository_venv": {
                "python": sys.version.split()[0],
                "matplotlib": matplotlib.__version__,
                "render_ms": local["local_ms"],
                "role": "where the skill's own tests run; tracks a newer matplotlib on purpose",
            },
            "parity_venv": {
                **(parity_result or {}).get("environment", {}),
                "role": "pinned to the versions the browser runs; this is the comparison "
                        "that decides equivalence",
                "error": parity_error,
            },
            "parity_status": parity.status(),
        },
        "cold_start": {
            "total_ms": payload.get("cold_start_ms"),
            "breakdown_ms": payload.get("boot", {}),
            "page_wall_s": round(wall, 2),
            "note": "Measured on a warm HTTP cache-less loopback server; a real network "
                    "adds transfer time for the %.1f MiB above." % lock["total_mib"],
        },
        "first_render": payload.get("first_render"),
        "hot_render_ms": {
            "samples": len(hot),
            "python_min": min(hot) if hot else None,
            "python_median": round(statistics.median(hot), 2) if hot else None,
            "python_p95": round(sorted(hot)[max(0, int(len(hot) * 0.95) - 1)], 2) if hot else None,
            "python_max": max(hot) if hot else None,
            "worker_wall_median": round(statistics.median(hot_wall), 2) if hot_wall else None,
            "worker_wall_p95": (round(sorted(hot_wall)[max(0, int(len(hot_wall) * 0.95) - 1)], 2)
                                if hot_wall else None),
            "definition": "python_* is figure_core's own timing inside the worker; "
                          "worker_wall_* adds the JSON round trip. Neither includes the "
                          "page inserting the SVG into the DOM.",
        },
        "invalid_spec_is_a_message_not_a_crash": payload.get("invalid_spec"),
        "svg_equivalence": {
            "against_parity_venv": parity_comparison,
            "against_repository_venv": comparison,
            "what_this_means": "against_parity_venv is the claim: same spec, same profile, "
                               "same matplotlib, byte-identical SVG. against_repository_venv "
                               "is reported for information — the repository venv runs a newer "
                               "matplotlib, and a difference there is a matplotlib version "
                               "difference, not evidence about the browser.",
        },
        "geometry": {
            "browser_width_mm": payload.get("width_mm"),
            "browser_height_mm": payload.get("height_mm"),
            "local_width_mm": local["width_mm"],
            "local_height_mm": local["height_mm"],
            "browser_viewbox": viewbox(payload.get("svg", "") or ""),
            "local_viewbox": viewbox(local["svg"]),
        },
        "console": console[:40],
        "page_errors": page_errors,
        "fatal": payload.get("fatal"),
    }

    checks = []
    checks.append(("worker_boots", payload.get("fatal") is None))
    checks.append(("first_render_ok", bool((payload.get("first_render") or {}).get("ok"))))
    checks.append(("invalid_spec_rejected",
                   (payload.get("invalid_spec") or {}).get("ok") is False))
    checks.append(("no_page_errors", not page_errors))
    checks.append(("svg_identical_to_parity_env",
                   bool(parity_comparison and parity_comparison["identical"])))
    checks.append(("geometry_matches",
                   abs((payload.get("width_mm") or 0) - local["width_mm"]) < 1e-6))
    report["checks"] = [{"id": name, "passed": bool(ok)} for name, ok in checks]
    report["status"] = "pass" if all(ok for _, ok in checks) else "fail"

    if keep_svg and payload.get("svg"):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(os.path.join(OUTPUT_DIR, "prototype-browser.svg"), "w", encoding="utf-8") as handle:
            handle.write(payload["svg"])
        with open(os.path.join(OUTPUT_DIR, "prototype-local.svg"), "w", encoding="utf-8") as handle:
            handle.write(local["svg"])
        if parity_result:
            with open(os.path.join(OUTPUT_DIR, "prototype-parity.svg"), "w", encoding="utf-8") as handle:
                handle.write(parity_result["svg"])

    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--samples", type=int, default=30, help="Hot renders to time (default 30).")
    parser.add_argument("--width-mm", type=float, default=ICML_COLUMN_MM,
                        help="Canvas width for the case (default: ICML's measured column).")
    parser.add_argument("--keep-svg", action="store_true", help="Also write both SVGs for inspection.")
    parser.add_argument("--timeout", type=int, default=300, help="Seconds allowed for the page.")
    args = parser.parse_args(argv)

    report = run(args.samples, args.width_mm, args.keep_svg, args.timeout)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, "pyodide-prototype.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    print("status: %s" % report["status"])
    for check in report["checks"]:
        print("  [%s] %s" % ("pass" if check["passed"] else "FAIL", check["id"]))
    cold = report["cold_start"]
    print("cold start: %s ms (%s MiB of runtime), breakdown %s"
          % (cold["total_ms"], report["runtime"]["download_mib"], cold["breakdown_ms"].get("runtime_ms")))
    hot = report["hot_render_ms"]
    print("hot render: median %s ms, p95 %s ms over %s samples (worker wall p95 %s ms)"
          % (hot["python_median"], hot["python_p95"], hot["samples"], hot["worker_wall_p95"]))
    equivalence = report["svg_equivalence"]
    for label, key in (("parity venv", "against_parity_venv"), ("repo venv", "against_repository_venv")):
        entry = equivalence.get(key)
        print("svg identical to %s: %s" % (label, entry["identical"] if entry else "not compared"))
    print("report: %s" % os.path.relpath(path, REPO_ROOT))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
