#!/usr/bin/env python3
"""Take what the tool exports, feed it back to the command line, and compare.

An export is only worth having if it reproduces the figure. So this does the
whole loop, for a handful of deliberately fiddly configurations:

  browser: pick a venue and width mode, move controls, render
    -> export the bundle exactly as the "Copy for an agent" button does
    -> local: validate the profile with the repository's own validator
    -> local: run render.py, which writes its ordinary five files
    -> compare the resulting figure.pdf's physical size against the slot,
       compare every resolved type value against the browser's,
       compare the SVG against the browser's byte for byte.

A profile that the validator rejects, a size that comes out different, or a
setting that did not survive the round trip is a failure — not a note.

    python scripts/verify_export_roundtrip.py
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
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

import figure_core  # noqa: E402
import parity  # noqa: E402
import render as render_module  # noqa: E402
from lab import open_lab  # noqa: E402

OUTPUT_DIR = os.path.join(TESTS_WEB, "calibration")
MM_PER_INCH = 25.4

CASES = [
    {"id": "icml-narrow-tuned", "venue": "icml2026", "layout": "narrow", "example": "line-multi",
     "controls": {"fonts.size_x_label_pt": 10.5, "fonts.size_y_label_pt": 7.5,
                  "fonts.size_ytick_pt": 6.5, "fonts.weight_x_label": "bold",
                  "lines.data_linewidth_pt": 1.8, "axes.max_yticks": 4}},
    {"id": "iclr-narrow-tuned", "venue": "iclr2026", "layout": "narrow", "example": "bar-signed",
     "controls": {"bar.category_label_rotation_deg": 30.0, "fonts.size_xtick_pt": 6.0,
                  "bar.width_fraction": 0.85, "fonts.weight_ytick": "bold"}},
    {"id": "neurips-wide-tuned", "venue": "neurips2026", "layout": "wide", "example": "line-many",
     "controls": {"fonts.size_legend_pt": 6.0, "fonts.weight_legend": "bold",
                  "lines.marker_size_pt": 2.5, "axes.grid_alpha": 0.75}},
]


def deep_equal_numbers(left: Any, right: Any, path: str = "") -> List[str]:
    """Differences between two JSON structures, as paths."""
    if isinstance(left, dict) and isinstance(right, dict):
        problems = []
        for key in sorted(set(left) | set(right)):
            if key not in left:
                problems.append("%s.%s missing on the left" % (path, key))
            elif key not in right:
                problems.append("%s.%s missing on the right" % (path, key))
            else:
                problems += deep_equal_numbers(left[key], right[key], "%s.%s" % (path, key))
        return problems
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return ["%s has %d vs %d entries" % (path, len(left), len(right))]
        problems = []
        for index, (a, b) in enumerate(zip(left, right)):
            problems += deep_equal_numbers(a, b, "%s[%d]" % (path, index))
        return problems
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        if abs(float(left) - float(right)) > 1e-9:
            return ["%s: %r vs %r" % (path, left, right)]
        return []
    return [] if left == right else ["%s: %r vs %r" % (path, left, right)]


def run_case(lab, case: Dict[str, Any]) -> Dict[str, Any]:
    lab.reset_all()
    lab.select(case["venue"], case["layout"])
    lab.page.select_option("#example", case["example"])
    lab.wait_for_render()
    for path, value in case["controls"].items():
        lab.set_control(path, value)
    browser_render = lab.wait_for_render()
    bundle = lab.export_bundle()
    text = lab.export_text()
    ready = lab.export_ready()
    page = lab.page_manifest()

    problems: List[str] = []
    if not ready:
        problems.append("the tool did not consider the configuration exportable")

    # 1. The exported profile is a profile, by the repository's own validator.
    try:
        validated = figure_core.validate_profile(json.loads(json.dumps(bundle["profile"])))
    except figure_core.ProfileError as exc:
        return {"id": case["id"], "status": "fail",
                "problems": ["the exported profile is not valid: %s" % exc]}

    # 2. Every control the case moved actually reached the exported profile.
    for path, value in case["controls"].items():
        section, _, key = path.partition(".")
        actual = bundle["profile"].get(section, {}).get(key)
        if isinstance(value, (int, float)):
            if actual is None or abs(float(actual) - float(value)) > 1e-9:
                problems.append("%s exported as %r, not %r" % (path, actual, value))
        elif actual != value:
            problems.append("%s exported as %r, not %r" % (path, actual, value))

    # 3. The width is the slot's, and it says so.
    if abs(bundle["profile"]["canvas"]["width_mm"] - page["figure"]["width_mm"]) > 1e-6:
        problems.append("exported width %s mm is not the slot's %s mm"
                        % (bundle["profile"]["canvas"]["width_mm"], page["figure"]["width_mm"]))

    # 4. The hand-off text carries the things it promises to carry.
    for needle in ("render.py", "profile.json", "spec.json",
                   bundle["target"]["venue"], "%.3f mm" % bundle["target"]["figure_width_mm"]):
        if needle not in text:
            problems.append("the hand-off text does not mention %r" % needle)

    # 5. Run render.py on the exported files, in the pinned environment, and
    #    compare with what the browser drew.
    workdir = tempfile.mkdtemp(prefix="mpf-roundtrip-")
    try:
        spec_path = os.path.join(workdir, "spec.json")
        profile_path = os.path.join(workdir, "profile.json")
        figure_core.write_json(spec_path, bundle["spec"])
        figure_core.write_json(profile_path, bundle["profile"])
        output_dir = os.path.join(workdir, "out")
        report = render_module.render(spec_path, output_dir, profile_path)

        expected_pt = (
            bundle["target"]["figure_width_mm"] / MM_PER_INCH * 72.0,
            bundle["target"]["figure_height_mm"] / MM_PER_INCH * 72.0,
        )
        from pypdf import PdfReader
        box = PdfReader(os.path.join(output_dir, "figure.pdf")).pages[0].mediabox
        for name, actual, expected in (("width", float(box.width), expected_pt[0]),
                                       ("height", float(box.height), expected_pt[1])):
            if abs(actual - expected) > 0.5:
                problems.append("figure.pdf %s is %.3f pt, expected %.3f pt"
                                % (name, actual, expected))

        resolved = figure_core.resolved_type(validated)
        browser_resolved = {
            role: {"size_pt": entry["size_pt"], "weight": entry["weight"]}
            for role, entry in bundle["resolved_type"].items()
        }
        problems += ["resolved type " + item
                     for item in deep_equal_numbers(resolved, browser_resolved)]

        local = parity.render_svg(bundle["spec"], bundle["profile"])
        svg_identical = local["svg"] == browser_render["svg"]
        if not svg_identical:
            problems.append("the re-rendered SVG is not byte-identical to the browser's")

        drawn_diff = deep_equal_numbers(report["drawn"], browser_render["drawn"])
        problems += ["drawn " + item for item in drawn_diff]

        result = {
            "id": case["id"],
            "venue": case["venue"], "layout": case["layout"], "example": case["example"],
            "controls": case["controls"],
            "status": "pass" if not problems else "fail",
            "problems": problems,
            "render_status": report["status"],
            "render_warnings": [
                {"id": entry["id"], "status": entry["status"], "message": entry["message"]}
                for entry in report["checks"] if entry["status"] in ("warn", "fail")
            ],
            "figure_pdf_pt": [round(float(box.width), 4), round(float(box.height), 4)],
            "expected_pdf_pt": [round(value, 4) for value in expected_pt],
            "svg_identical_to_browser": svg_identical,
            "resolved_type": resolved,
            "handoff_characters": len(text),
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return result


def run() -> Dict[str, Any]:
    results = []
    with open_lab() as lab:
        environment = lab.wait_ready()
        lab.wait_for_render()
        for case in CASES:
            results.append(run_case(lab, case))
            entry = results[-1]
            print("  %-22s %-5s %s" % (entry["id"], entry["status"],
                                       "; ".join(entry["problems"])[:160]))
        page_errors = list(lab.page_errors)

    report = {
        "report_version": "1",
        "kind": "export-roundtrip",
        "status": "pass" if all(r["status"] == "pass" for r in results) and not page_errors else "fail",
        "claim": "What the tool exports, fed back to render.py unchanged, reproduces the "
                 "figure the preview showed: same physical size, same resolved type, "
                 "byte-identical SVG.",
        "note": "The exported profile is validated by the repository's own validator before "
                "anything else happens, so an export carrying metadata the validator would "
                "reject fails here rather than at the receiving agent.",
        "browser_environment": environment,
        "local_environment": parity.status(),
        "cases": results,
        "page_errors": page_errors,
    }
    import web_fingerprint
    web_fingerprint.stamp(report)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, "export-roundtrip.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print("report: %s" % os.path.relpath(path, REPO_ROOT))
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    return 0 if run()["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
