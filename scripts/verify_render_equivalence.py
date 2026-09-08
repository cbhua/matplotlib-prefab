#!/usr/bin/env python3
"""Does the browser draw the same figure the command line draws? Measure it.

The tool's central claim is that what you see in the preview is what
``render.py`` produces. This checks it the only way that means anything: the
same spec and the same profile are drawn in the browser and in a local
interpreter pinned to the versions the browser runs, and the two SVGs are
compared byte for byte.

Byte-for-byte is achievable here because ``figure_core.figure_to_svg`` fixes the
element-id salt and suppresses the date — the two things in a matplotlib SVG
that are otherwise per-run. Nothing else is normalised; a difference in the
comparison is a difference in the drawing.

The matrix covers both chart kinds, both extremes of the width modes, and the
edge settings that a slider makes easy to reach: very small type, very large
type, heavy lines, rotated category labels, per-axis sizes and weights.

    python scripts/verify_render_equivalence.py
    python scripts/verify_render_equivalence.py --keep-svg

Also measures hot render latency in the real page, because the same session can
answer both questions and the numbers belong in the same report.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import statistics
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SKILL_SCRIPTS = os.path.join(REPO_ROOT, "skills", "scientific-figures", "scripts")
TESTS_WEB = os.path.join(REPO_ROOT, "tests", "web")
for path in (SKILL_SCRIPTS, SCRIPTS, TESTS_WEB):
    if path not in sys.path:
        sys.path.insert(0, path)

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import parity  # noqa: E402
from lab import open_lab  # noqa: E402

OUTPUT_DIR = os.path.join(TESTS_WEB, "calibration")
GENERATED = os.path.join(REPO_ROOT, "web", "public", "generated")

# The interaction target from the plan: after a slider stops, a redraw within
# half a second at the 95th percentile, over at least thirty measurements.
LATENCY_TARGET_MS = 500.0
LATENCY_SAMPLES = 40


def load(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def cases() -> List[Dict[str, Any]]:
    """Spec, venue/mode and profile edits for each case in the matrix."""
    return [
        {"id": "line-default-icml-narrow", "spec": "line-multi",
         "venue": "icml2026", "layout": "narrow", "edits": {},
         "why": "the default the tool opens on"},
        {"id": "bar-default-icml-narrow", "spec": "bar-signed",
         "venue": "icml2026", "layout": "narrow", "edits": {},
         "why": "the other chart kind at the same width"},
        {"id": "line-default-iclr-narrow", "spec": "line-multi",
         "venue": "iclr2026", "layout": "narrow", "edits": {},
         "why": "the narrowest slot in the matrix"},
        {"id": "line-default-icml-wide", "spec": "line-multi",
         "venue": "icml2026", "layout": "wide", "edits": {},
         "why": "the widest slot in the matrix"},
        {"id": "line-tiny-type", "spec": "line-multi",
         "venue": "iclr2026", "layout": "narrow",
         "edits": {"fonts.size_xtick_pt": 4.0, "fonts.size_ytick_pt": 4.0,
                   "fonts.size_x_label_pt": 5.0, "fonts.size_y_label_pt": 5.0,
                   "fonts.size_legend_pt": 4.5},
         "why": "type small enough that the layout engine has slack it does not usually have"},
        {"id": "line-large-type", "spec": "line-multi",
         "venue": "iclr2026", "layout": "narrow",
         "edits": {"fonts.size_xtick_pt": 14.0, "fonts.size_ytick_pt": 14.0,
                   "fonts.size_x_label_pt": 16.0, "fonts.size_y_label_pt": 16.0,
                   "fonts.size_title_pt": 18.0},
         "why": "type large enough to crowd the panel; the checks should say so, in both places"},
        {"id": "line-per-axis-and-weights", "spec": "line-multi",
         "venue": "neurips2026", "layout": "wide",
         "edits": {"fonts.size_x_label_pt": 11.0, "fonts.size_y_label_pt": 7.0,
                   "fonts.size_xtick_pt": 6.0, "fonts.size_ytick_pt": 10.0,
                   "fonts.weight_x_label": "bold", "fonts.weight_ytick": "bold",
                   "fonts.weight_legend": "bold", "fonts.weight_title": "bold"},
         "why": "every per-axis override at once, sizes and weights, all different"},
        {"id": "line-heavy-lines", "spec": "line-many",
         "venue": "neurips2026", "layout": "narrow",
         "edits": {"lines.data_linewidth_pt": 3.0, "lines.axes_linewidth_pt": 2.0,
                   "lines.marker_size_pt": 9.0, "axes.grid_alpha": 0.9,
                   "axes.grid_linewidth_pt": 1.5},
         "why": "heavy strokes and a dense grid, with the most series the palette allows"},
        {"id": "bar-rotated-labels", "spec": "bar-signed",
         "venue": "iclr2026", "layout": "narrow",
         "edits": {"bar.category_label_rotation_deg": 45.0, "bar.width_fraction": 0.95,
                   "bar.edge_linewidth_pt": 0.8, "fonts.size_xtick_pt": 5.0},
         "why": "rotated category labels, which change the layout as well as the drawing"},
        {"id": "line-single-no-legend", "spec": "line-single",
         "venue": "icml2026", "layout": "wide",
         "edits": {"axes.max_xticks": 12, "axes.max_yticks": 3, "lines.tick_length_pt": 6.0,
                   "lines.tick_pad_pt": 8.0},
         "why": "tick counts and tick geometry pushed to their ends"},
    ]


def apply_edits(profile: Dict[str, Any], edits: Dict[str, Any]) -> Dict[str, Any]:
    edited = copy.deepcopy(profile)
    for path, value in edits.items():
        section, _, key = path.partition(".")
        edited[section][key] = value
    return edited


def compare(browser_svg: str, local_svg: str) -> Dict[str, Any]:
    if browser_svg == local_svg:
        return {"identical": True, "bytes": len(browser_svg)}
    limit = min(len(browser_svg), len(local_svg))
    index = next((i for i in range(limit) if browser_svg[i] != local_svg[i]), limit)
    return {
        "identical": False,
        "browser_bytes": len(browser_svg),
        "local_bytes": len(local_svg),
        "first_difference_at": index,
        "browser": browser_svg[max(0, index - 80):index + 80],
        "local": local_svg[max(0, index - 80):index + 80],
    }


def run(keep_svg: bool, latency_samples: int) -> Dict[str, Any]:
    base_profile = load(os.path.join(GENERATED, "profiles", "single-column.json"))
    specs = {
        name: load(os.path.join(GENERATED, "specs", "%s.json" % name))
        for name in ("line-multi", "line-single", "line-many", "bar-signed", "bar-positive")
    }
    pages = {
        (entry["venue"], entry["layout"]): load(os.path.join(
            GENERATED, "conferences", entry["venue"], entry["layout"], "page.json"))
        for entry in load(os.path.join(GENERATED, "conferences", "index.json"))["pages"]
    }

    results: List[Dict[str, Any]] = []
    latency: Dict[str, Any] = {}
    environment: Dict[str, Any] = {}

    with open_lab() as lab:
        environment = lab.wait_ready()
        lab.wait_for_render()

        for case in cases():
            page = pages[(case["venue"], case["layout"])]
            profile = apply_edits(base_profile, case["edits"])
            profile["canvas"]["width_mm"] = page["figure"]["width_mm"]
            spec = specs[case["spec"]]

            reply = lab.render_once(spec, profile)
            if not reply["result"].get("ok"):
                results.append({**case, "status": "fail",
                                "error": reply["result"].get("error")})
                continue
            browser_svg = reply["result"]["svg"]
            local = parity.render_svg(spec, profile)
            comparison = compare(browser_svg, local["svg"])
            results.append({
                "id": case["id"], "why": case["why"], "spec": case["spec"],
                "venue": case["venue"], "layout": case["layout"], "edits": case["edits"],
                "status": "pass" if comparison["identical"] else "fail",
                "comparison": comparison,
                "browser_size_mm": [reply["result"]["width_mm"], reply["result"]["height_mm"]],
                "local_size_mm": [local["width_mm"], local["height_mm"]],
                "browser_render_ms": reply["result"]["render_ms"],
            })
            if keep_svg:
                directory = os.path.join(OUTPUT_DIR, "equivalence", case["id"])
                os.makedirs(directory, exist_ok=True)
                for name, payload in (("browser.svg", browser_svg), ("local.svg", local["svg"])):
                    with open(os.path.join(directory, name), "w", encoding="utf-8") as handle:
                        handle.write(payload)

        # Latency, in the real page, through the real controls: set a value,
        # wait until the sheet is showing that configuration. That includes the
        # debounce, the worker round trip and putting the SVG in the DOM, which
        # is what "how long until I see it" actually means.
        lab.reset_all()
        lab.wait_for_render()
        samples = []
        for index in range(latency_samples):
            value = 7.0 + (index % 9) * 0.5
            started = time.perf_counter()
            lab.set_control("fonts.size_x_label_pt", value)
            lab.wait_for_render()
            samples.append((time.perf_counter() - started) * 1000.0)
        ordered = sorted(samples)
        latency = {
            "samples": len(samples),
            "measures": "from setting a control to the page showing that configuration, "
                        "including the debounce, the worker round trip and the DOM update",
            "debounce_ms": 120,
            "min_ms": round(min(samples), 1),
            "median_ms": round(statistics.median(samples), 1),
            "p95_ms": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 1),
            "max_ms": round(max(samples), 1),
            "target_p95_ms": LATENCY_TARGET_MS,
            "meets_target": ordered[max(0, int(len(ordered) * 0.95) - 1)] <= LATENCY_TARGET_MS,
        }
        heap = lab.javascript_heap_bytes()
        browser_version = lab.browser_version
        page_errors = list(lab.page_errors)

    failures = [entry for entry in results if entry["status"] != "pass"]
    report = {
        "report_version": "1",
        "kind": "render-equivalence",
        "status": "pass" if not failures and latency["meets_target"] and not page_errors else "fail",
        "claim": "The same spec and profile, drawn by the same shared code, produce a "
                 "byte-identical SVG in the browser and in a local interpreter pinned to the "
                 "versions the browser runs.",
        "not_claimed": "Nothing here says a different matplotlib would draw the same thing, "
                       "or that this style over different data gives the same figure. Both "
                       "are false and the export says so.",
        "browser": {"engine": "chromium", "version": browser_version},
        "browser_environment": environment,
        "local_environment": parity.status(),
        "cases": results,
        "latency": latency,
        "javascript_heap_bytes_after": heap,
        "page_errors": page_errors,
    }
    import web_fingerprint
    web_fingerprint.stamp(report)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, "render-equivalence.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    for entry in results:
        print("  %-28s %-5s %s" % (entry["id"], entry["status"],
                                   "" if entry["status"] == "pass"
                                   else entry.get("error") or entry["comparison"]))
    print("latency: median %s ms, p95 %s ms over %d samples (target p95 <= %s ms) -> %s"
          % (latency["median_ms"], latency["p95_ms"], latency["samples"],
             LATENCY_TARGET_MS, "met" if latency["meets_target"] else "NOT MET"))
    print("report: %s" % os.path.relpath(path, REPO_ROOT))
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep-svg", action="store_true")
    parser.add_argument("--latency-samples", type=int, default=LATENCY_SAMPLES)
    args = parser.parse_args(argv)
    report = run(args.keep_svg, args.latency_samples)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
