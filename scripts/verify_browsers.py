#!/usr/bin/env python3
"""Run the tool in each browser engine available here, and say which were tested.

Chromium is the calibration baseline: the millimetre thresholds in
``compare_pages.py`` were measured against it. The other engines are checked for
something weaker but still worth knowing — that the tool loads, that Pyodide
runs, that a figure is drawn at the right physical size, and that the layout
does not fall apart.

An engine that cannot be launched here is reported as *not tested*. It is not
reported as passing, and the coverage this project claims is whatever this file
last wrote down.

    python scripts/verify_browsers.py
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_WEB = os.path.join(REPO_ROOT, "tests", "web")
for path in (TESTS_WEB, os.path.dirname(os.path.abspath(__file__))):
    if path not in sys.path:
        sys.path.insert(0, path)

from server import static_server  # noqa: E402
from lab import Lab  # noqa: E402

OUTPUT = os.path.join(TESTS_WEB, "calibration", "browsers.json")
ENGINES = ("chromium", "firefox", "webkit")
HOT_SAMPLES = 12


def probe(playwright, engine: str, origin: str) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"engine": engine, "tested": False}
    try:
        browser_type = getattr(playwright, engine)
        browser = browser_type.launch()
    except Exception as exc:
        entry["reason_not_tested"] = str(exc).strip().splitlines()[0][:400]
        entry["detail"] = ("This engine could not be launched in this environment, so nothing "
                           "is known about it here. It is not being reported as working.")
        return entry

    try:
        context = browser.new_context(viewport={"width": 1400, "height": 1100})
        page = context.new_page()
        errors: List[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        started = time.perf_counter()
        page.goto(origin + "/index.html")
        Lab(page, origin, browser.version).wait_ready()
        page.wait_for_function(
            "window.__labApi && (window.__labApi.ready() || window.__labApi.bootError())",
            timeout=300_000,
        )
        boot_error = page.evaluate("window.__labApi.bootError()")
        entry.update({"tested": True, "version": browser.version,
                      "boot_seconds": round(time.perf_counter() - started, 2)})
        if boot_error:
            entry.update({"status": "fail", "boot_error": str(boot_error)[:600]})
            return entry

        page.wait_for_function(
            "() => { const g = window.__labApi.lastGood();"
            " return g && g.signature === window.__labApi.signature(); }",
            timeout=300_000,
        )
        first = page.evaluate("window.__labApi.lastGood()")
        manifest = page.evaluate("window.__labApi.currentPage()")

        samples = []
        for index in range(HOT_SAMPLES):
            value = 7.0 + (index % 7) * 0.5
            begin = time.perf_counter()
            page.evaluate("v => window.__labApi.setControl('fonts.size_x_label_pt', v)", value)
            page.wait_for_function(
                "() => { const g = window.__labApi.lastGood();"
                " return g && g.signature === window.__labApi.signature(); }",
                timeout=120_000,
            )
            samples.append((time.perf_counter() - begin) * 1000.0)

        # Layout sanity: the sheet is the sheet, whatever the engine.
        geometry = page.evaluate(
            # offsetWidth/offsetHeight, not getBoundingClientRect: the preview
            # applies a display zoom as a transform on an ancestor, and the
            # client rect would report the zoomed size. The sheet's own layout
            # size is the one that must be right.
            """() => { const p = document.querySelector('.mpf-paper');
                       return {width: p.offsetWidth, height: p.offsetHeight,
                               runs: document.querySelectorAll('text.mpf-run').length,
                               slot: document.querySelector('.mpf-slot svg') !== null,
                               fonts: [...document.fonts].filter(f => f.status === 'loaded').length}; }"""
        )
        expected = [manifest["paper"]["width_pt"] * 96 / 72, manifest["paper"]["height_pt"] * 96 / 72]
        ordered = sorted(samples)
        checks = [
            ("figure_drawn", bool(first and first.get("svg")), ""),
            ("figure_at_slot_width",
             abs(first["width_mm"] - manifest["figure"]["width_mm"]) < 1e-6,
             "%.4f vs %.4f mm" % (first["width_mm"], manifest["figure"]["width_mm"])),
            ("sheet_is_the_right_size",
             abs(geometry["width"] - expected[0]) < 0.5 and abs(geometry["height"] - expected[1]) < 0.5,
             "%s vs %s CSS px" % ([geometry["width"], geometry["height"]],
                                  [round(v, 2) for v in expected])),
            ("body_text_present", geometry["runs"] > 100, "%d runs" % geometry["runs"]),
            ("figure_in_the_slot", geometry["slot"], ""),
            ("fonts_loaded", geometry["fonts"] > 0, "%d faces" % geometry["fonts"]),
            ("no_page_errors", not errors, "; ".join(errors)[:200]),
        ]
        # Latency is measured on every engine but only *targeted* on the
        # baseline one. Reporting Firefox against a threshold chosen for
        # Chromium would either fail it for no reason or, worse, invite the
        # threshold to be raised until everything passes.
        target_applies = engine == "chromium"
        entry.update({
            "status": "pass" if all(ok for _, ok, _ in checks) else "fail",
            "checks": [{"id": name, "passed": bool(ok), "detail": detail}
                       for name, ok, detail in checks],
            "environment": page.evaluate("window.__lab.environment"),
            "first_render_ms": first["render_ms"],
            "interaction_ms": {
                "samples": len(samples),
                "median": round(statistics.median(samples), 1),
                "p95": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 1),
                "max": round(max(samples), 1),
                "target_p95_ms": 500.0 if target_applies else None,
                "meets_target": (ordered[max(0, int(len(ordered) * 0.95) - 1)] <= 500.0
                                 if target_applies else None),
                "note": ("The interaction target is set for the baseline engine. This is a "
                         "smaller sample than the equivalence run's and is here to show the "
                         "order of magnitude on this engine, not to certify it."),
            },
            "sheet_css_px": [geometry["width"], geometry["height"]],
        })
        context.close()
        return entry
    finally:
        browser.close()


def run(engines: Sequence[str]) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright

    results = []
    with static_server(os.path.join(REPO_ROOT, "web")) as origin:
        with sync_playwright() as playwright:
            for engine in engines:
                entry = probe(playwright, engine, origin)
                results.append(entry)
                if entry["tested"]:
                    print("  %-9s %-12s %-5s  first %s ms, interaction p95 %s ms"
                          % (engine, entry.get("version", ""), entry.get("status"),
                             entry.get("first_render_ms"),
                             (entry.get("interaction_ms") or {}).get("p95")))
                    for check in entry.get("checks", []):
                        if not check["passed"]:
                            print("      [FAIL] %s: %s" % (check["id"], check["detail"]))
                else:
                    print("  %-9s not tested: %s" % (engine, entry["reason_not_tested"]))

    tested = [entry for entry in results if entry["tested"]]
    report = {
        "report_version": "1",
        "kind": "browser-coverage",
        "status": "pass" if tested and all(e["status"] == "pass" for e in tested) else "fail",
        "baseline_engine": "chromium",
        "baseline_note": "The millimetre thresholds in the page calibration were measured "
                         "against Chromium. Other engines are checked for loading, running "
                         "Pyodide, drawing at the right physical size and holding the sheet "
                         "geometry — not for pixel-level agreement with the PDF.",
        "engines_tested": [entry["engine"] for entry in tested],
        "engines_not_tested": [
            {"engine": entry["engine"], "reason": entry["reason_not_tested"]}
            for entry in results if not entry["tested"]
        ],
        "coverage_claim": "Only the engines under engines_tested were run. An engine listed "
                          "under engines_not_tested is unknown here — not working, not broken.",
        "engines": results,
    }
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print("report: %s" % os.path.relpath(OUTPUT, REPO_ROOT))
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--engine", action="append", choices=ENGINES)
    args = parser.parse_args(argv)
    report = run(args.engine or ENGINES)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
