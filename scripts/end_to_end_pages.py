#!/usr/bin/env python3
"""The whole claim, end to end: browser page versus a LaTeX page built from its export.

Everything else in this project checks one link. This checks the chain. For each
venue, each width mode and each chart kind:

  the browser draws the figure and exports its configuration
    -> render.py redraws it locally from that export alone
    -> the venue's own LaTeX template compiles it into a real body page
    -> that page is rasterised, the browser's page is screenshotted at the same
       resolution, and the two are compared — figure included, nothing masked.

If the browser's preview and the compiled page disagree, this is where it shows,
because nothing is hidden: the figure, its caption, the prose beside it and the
running head are all in the comparison.

    python scripts/end_to_end_pages.py            # the 12 default pages
    python scripts/end_to_end_pages.py --tuned    # plus one edited case per venue
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
TESTS_DIR = os.path.join(REPO_ROOT, "tests")
TESTS_WEB = os.path.join(TESTS_DIR, "web")
for path in (SKILL_SCRIPTS, SCRIPTS, TESTS_DIR, TESTS_WEB):
    if path not in sys.path:
        sys.path.insert(0, path)

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import compare_pages  # noqa: E402
import evaluate_context  # noqa: E402
import figure_core  # noqa: E402
import render as render_module  # noqa: E402
import render_conference_context as rcc  # noqa: E402
from lab import open_lab  # noqa: E402

OUTPUT_DIR = os.path.join(TESTS_WEB, "calibration", "end-to-end")
COMPARE_DPI = compare_pages.COMPARE_DPI

# The same caption the baselines were generated with, so the compiled page and
# the calibrated page are the same page. A different caption would reflow the
# text under the figure and every comparison below would be measuring that.
CAPTION = evaluate_context.escape_tex(
    "Synthetic evaluation fixture, not a result. The panel above occupies "
    "exactly the width this template gives a figure in this mode, so its type "
    "prints at the size it is drawn at. The surrounding prose is an excerpt "
    "reproduced as typographic context; this page is not a paper and not a "
    "submission."
)

EXAMPLES = ("line-multi", "bar-signed")

TUNED = {
    "iclr2026": {"fonts.size_xtick_pt": 6.5, "fonts.weight_x_label": "bold",
                 "lines.data_linewidth_pt": 1.8},
    "neurips2026": {"fonts.size_y_label_pt": 11.0, "fonts.size_ytick_pt": 6.0,
                    "axes.grid_alpha": 0.8},
    "icml2026": {"fonts.size_x_label_pt": 7.0, "fonts.size_y_label_pt": 7.0,
                 "lines.marker_size_pt": 2.0, "axes.max_yticks": 4},
}

# Thresholds for the end-to-end comparison. Looser than the text-only page
# calibration on the image statistic, because two different rasterisers now have
# a *drawing* to disagree about as well as type, and tighter than nothing:
# a real misplacement moves the best whole-image alignment, which is checked.
THRESHOLDS = {
    "alignment_mm": 0.2,
    "placed_width_mm": 0.2,
    "ink_ratio_range": [0.9, 1.1],
}


# Capture-only styling, injected by the driver rather than shipped in the app.
# The sheet is pinned to the viewport's top-left corner so the screenshot's clip
# lands on whole device pixels: an element sitting at a fractional offset makes
# the browser round the capture outwards, and the result is a raster three pixels
# taller than the PDF's, which is not a difference in the page.
CAPTURE_CSS = """
.paper-scale { transform: none !important; filter: none !important; }
.mpf-paper { position: fixed !important; left: 0 !important; top: 0 !important; z-index: 99999; }
"""


def screenshot_paper(lab, path: str) -> None:
    lab.page.eval_on_selector("#zoom", "node => { node.value = '1'; "
                                       "node.dispatchEvent(new Event('input')); }")
    lab.page.wait_for_timeout(120)
    handle = lab.page.evaluate_handle(
        """(css) => { const style = document.createElement('style');
                      style.textContent = css; document.head.appendChild(style);
                      window.scrollTo(0, 0); return style; }""",
        CAPTURE_CSS,
    )
    try:
        size = lab.page.evaluate(
            """() => { const r = document.querySelector('.mpf-paper').getBoundingClientRect();
                       return {x: r.x, y: r.y, width: r.width, height: r.height}; }"""
        )
        lab.page.screenshot(path=path, clip=size, animations="disabled")
    finally:
        lab.page.evaluate("(style) => style.remove()", handle)


def one_case(lab, fixtures, venue: str, layout: str, example: str,
             controls: Optional[Dict[str, Any]], case_id: str,
             timeout: int) -> Dict[str, Any]:
    lab.reset_all()
    lab.select(venue, layout)
    lab.page.select_option("#example", example)
    lab.wait_for_render()
    for path, value in (controls or {}).items():
        lab.set_control(path, value)
    browser_render = lab.wait_for_render()
    bundle = lab.export_bundle()
    page_manifest = lab.page_manifest()

    directory = os.path.join(OUTPUT_DIR, venue, layout, case_id)
    os.makedirs(directory, exist_ok=True)
    browser_png = os.path.join(directory, "browser.png")
    screenshot_paper(lab, browser_png)

    workdir = tempfile.mkdtemp(prefix="mpf-e2e-")
    try:
        spec_path = os.path.join(workdir, "spec.json")
        profile_path = os.path.join(workdir, "profile.json")
        figure_core.write_json(spec_path, bundle["spec"])
        figure_core.write_json(profile_path, bundle["profile"])
        figure_dir = os.path.join(workdir, "figure")
        render_report = render_module.render(spec_path, figure_dir, profile_path)

        context_report = evaluate_context.evaluate(
            fixtures=fixtures, venue_id=venue, layout_id=layout, case_id=case_id,
            output_dir=directory, figure_dir=figure_dir, caption=CAPTION,
            png_dpi=compare_pages.REVIEW_DPI, timeout=timeout,
        )
        # The comparison raster lives in the scratch directory: `page.png`, which
        # the evaluator has already written beside `page.pdf`, is the same page
        # and is the one a person opens. Keeping a second full-page raster of it
        # in the repository would be evidence of nothing.
        latex_png = os.path.join(workdir, "latex.png")
        compare_pages.rasterise(os.path.join(directory, "page.pdf"), latex_png, COMPARE_DPI)

        baseline = compare_pages.load_grey(latex_png)
        browser = compare_pages.load_grey(browser_png)
        raster_sizes = {"latex": list(baseline.size), "browser": list(browser.size)}
        sizes_agree = baseline.size == browser.size
        baseline, browser = compare_pages.align_sizes(baseline, browser)
        stats, diff = compare_pages.difference_stats(baseline, browser)
        stats["ink_coverage"] = {
            "latex": round(compare_pages.ink_coverage(baseline), 6),
            "browser": round(compare_pages.ink_coverage(browser), 6),
        }
        stats["ink_coverage"]["ratio"] = round(
            stats["ink_coverage"]["browser"] / stats["ink_coverage"]["latex"], 5)
        stats["alignment"] = compare_pages.best_shift(baseline, browser)
        compare_pages.write_overlay(baseline, browser, os.path.join(directory, "overlay.png"))
        from PIL import ImageChops
        compare_pages.save_review(ImageChops.invert(diff), os.path.join(directory, "difference.png"))
        compare_pages.save_review(browser, browser_png)

        drift_mm = (max(abs(v) for v in stats["alignment"]["best_offset_px"])
                    * stats["alignment"]["pixel_mm"])
        width_error = abs(context_report["geometry"]["placed_width_mm"]
                          - page_manifest["figure"]["width_mm"])
        ratio = stats["ink_coverage"]["ratio"]

        checks = [
            ("figure_placed_at_slot_width", width_error <= THRESHOLDS["placed_width_mm"],
             "LaTeX placed it at %.4f mm; the browser drew %.4f mm"
             % (context_report["geometry"]["placed_width_mm"], page_manifest["figure"]["width_mm"])),
            ("placed_at_scale_one",
             abs(context_report["geometry"]["scale"] - 1.0) <= 0.005,
             "scale %.5f" % context_report["geometry"]["scale"]),
            ("raster_sizes_agree", sizes_agree,
             "browser %s vs LaTeX %s pixels" % (raster_sizes["browser"], raster_sizes["latex"])),
            ("no_page_drift", drift_mm <= THRESHOLDS["alignment_mm"],
             "best whole-image alignment %s px = %.4f mm"
             % (stats["alignment"]["best_offset_px"], drift_mm)),
            ("ink_within_range",
             THRESHOLDS["ink_ratio_range"][0] <= ratio <= THRESHOLDS["ink_ratio_range"][1],
             "browser/LaTeX ink coverage ratio %.4f" % ratio),
            ("context_no_failures", context_report["status"] != "fail",
             "context evaluation is %s" % context_report["status"]),
        ]

        return {
            "id": case_id, "venue": venue, "layout": layout, "example": example,
            "controls": controls or {},
            "status": "pass" if all(ok for _, ok, _ in checks) else "fail",
            "checks": [{"id": name, "passed": bool(ok), "detail": detail}
                       for name, ok, detail in checks],
            "figure": {
                "browser_width_mm": browser_render["width_mm"],
                "browser_height_mm": browser_render["height_mm"],
                "placed_width_mm": context_report["geometry"]["placed_width_mm"],
                "scale": context_report["geometry"]["scale"],
                "slot_width_mm": page_manifest["slot"]["width_mm"],
            },
            "render_status": render_report["status"],
            "render_warnings": [
                {"id": entry["id"], "status": entry["status"], "message": entry["message"]}
                for entry in render_report["checks"] if entry["status"] in ("warn", "fail")
            ],
            "context_status": context_report["status"],
            "context_page": context_report["page"]["printed_page_number"],
            "image": stats,
            "raster_sizes": raster_sizes,
            "image_dpi": compare_pages.REVIEW_DPI,
            "image_note": "The kept images are %d DPI for review; the comparison was made "
                          "at %d DPI." % (compare_pages.REVIEW_DPI, COMPARE_DPI),
            "resolved_type": bundle["resolved_type"],
            "outputs": {
                name: os.path.relpath(os.path.join(directory, name), REPO_ROOT)
                for name in ("browser.png", "page.png", "overlay.png", "difference.png",
                             "page.pdf", "context-report.json")
            },
            "outputs_legend": {
                "browser.png": "the tool's own sheet, screenshotted",
                "page.png": "the LaTeX page it is being compared with",
                "overlay.png": "LaTeX in red, browser in blue; agreement is magenta",
                "difference.png": "per-pixel difference, inverted",
                "page.pdf": "the compiled page itself, at full fidelity",
            },
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def run(include_tuned: bool, timeout: int) -> Dict[str, Any]:
    fixtures = rcc.fixtures()
    results: List[Dict[str, Any]] = []
    # The screenshot has to come out at the same resolution as the PDF raster,
    # so the browser is run at the device pixel ratio that makes 96 CSS pixels
    # per inch into the comparison DPI.
    # The viewport has to be taller than the sheet (1056 CSS px for US Letter):
    # a clipped screenshot cannot capture below the fold, and a short viewport
    # would silently return a cropped page.
    with open_lab(device_scale_factor=COMPARE_DPI / 96.0, viewport=(1500, 1200)) as lab:
        environment = lab.wait_ready()
        lab.wait_for_render()
        for venue in rcc.VENUES:
            for layout in fixtures.layout_ids(venue):
                for example in EXAMPLES:
                    result = one_case(lab, fixtures, venue, layout, example, None,
                                      "default-%s" % example, timeout)
                    results.append(result)
                    print("  %-12s %-7s %-18s %-5s  %s" % (
                        venue, layout, example, result["status"],
                        "; ".join(c["detail"] for c in result["checks"] if not c["passed"])[:110]))
            if include_tuned:
                result = one_case(lab, fixtures, venue, "narrow", "line-multi",
                                  TUNED[venue], "tuned-line-multi", timeout)
                results.append(result)
                print("  %-12s %-7s %-18s %-5s  %s" % (
                    venue, "narrow", "tuned line-multi", result["status"],
                    "; ".join(c["detail"] for c in result["checks"] if not c["passed"])[:110]))
        page_errors = list(lab.page_errors)

    report = {
        "report_version": "1",
        "kind": "end-to-end-pages",
        "status": "pass" if all(r["status"] == "pass" for r in results) and not page_errors else "fail",
        "claim": "A page previewed in the browser and the same page compiled by the venue's "
                 "own LaTeX from the browser's export are the same page, figure included.",
        "not_claimed": "This says nothing about *your* paper: your float may land elsewhere, "
                       "your macros may differ, and your data will change the figure's own "
                       "layout. It says the tool's page and the template's page agree.",
        "thresholds": THRESHOLDS,
        "comparison_dpi": COMPARE_DPI,
        "browser_environment": environment,
        "cases": results,
        "page_errors": page_errors,
    }
    import web_fingerprint
    web_fingerprint.stamp(report)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, "end-to-end.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print("report: %s" % os.path.relpath(path, REPO_ROOT))
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tuned", action="store_true",
                        help="Also run one deliberately edited case per venue.")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args(argv)
    absent = evaluate_context.missing_tools()
    if absent:
        print("error: needs %s." % ", ".join(sorted(absent)), file=sys.stderr)
        return 3
    return 0 if run(args.tuned, args.timeout)["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
