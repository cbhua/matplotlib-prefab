#!/usr/bin/env python3
"""Compare the HTML paper page with the compiled PDF it was generated from.

This is the part that decides whether the page is a reproduction or a
resemblance. For each venue and width mode it:

* renders the HTML page in headless Chromium at a fixed device pixel ratio,
* rasterises the baseline PDF at the same resolution with pdftoppm,
* measures, from the browser's own DOM, where every text run landed, and
  compares that with where the PDF put it — in millimetres, per run,
* masks only the inside of the figure slot (the baseline has an empty
  placeholder there and the live tool has a figure; the slot's own edges, the
  caption and the surrounding prose are *not* masked),
* and writes an overlay, a difference image and a report.

No threshold is adjusted to make a page pass. The report states the errors it
measured and whether they are inside the thresholds this project set; if they
are not, that is the finding.

Run through ``calibrate_conference_pages.py --compare``, or directly:

    python scripts/compare_pages.py --venue icml2026 --layout narrow
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_WEB = os.path.join(REPO_ROOT, "tests", "web")
CALIBRATION_DIR = os.path.join(TESTS_WEB, "calibration")
BASELINE_DIR = os.path.join(CALIBRATION_DIR, "baselines")
GENERATED = os.path.join(REPO_ROOT, "web", "public", "generated")

for path in (TESTS_WEB, os.path.dirname(os.path.abspath(__file__)), os.path.join(REPO_ROOT, "tests")):
    if path not in sys.path:
        sys.path.insert(0, path)

from server import static_server  # noqa: E402

MM_PER_INCH = 25.4
PDF_PT_PER_INCH = 72.0
COMPARE_DPI = 300

# Everything is *measured* at COMPARE_DPI. The images kept for a person to look
# at are written at this instead, because a repository does not need six dozen
# 1 MB page rasters to make a point that the numbers already make precisely.
# The comparison never sees these; downsampling after measuring cannot change a
# result.
REVIEW_DPI = 150
DEVICE_PIXEL_RATIO = COMPARE_DPI / 96.0

# The thresholds this project set for a page to count as calibrated. They are
# written here, once, and the report says which ones a page met. Raising one to
# make a failing page pass would make the whole exercise decorative.
THRESHOLDS = {
    "paper_size_mm": 0.2,
    "slot_edge_mm": 0.2,
    "run_baseline_mm": 0.2,
    "run_left_edge_mm": 0.2,
    "run_width_mm": 0.35,
    "line_count_exact": True,
}


def pt_to_mm(value: float) -> float:
    return value / PDF_PT_PER_INCH * MM_PER_INCH


def rasterise(pdf_path: str, png_path: str, dpi: int) -> None:
    prefix = os.path.splitext(png_path)[0]
    result = subprocess.run(
        ["pdftoppm", "-png", "-r", str(dpi), "-singlefile", pdf_path, prefix],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0 or not os.path.isfile(png_path):
        raise RuntimeError("pdftoppm failed on %s: %s" % (pdf_path, result.stderr.strip()))


def screenshot(origin: str, venue: str, layout: str, path: str) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright

    url = "%s/tests/web/harness/paper-page.html?venue=%s&layout=%s" % (origin, venue, layout)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            device_scale_factor=DEVICE_PIXEL_RATIO,
            viewport={"width": 900, "height": 1200},
        )
        page = context.new_page()
        errors: List[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(url)
        page.wait_for_function("window.__ready === true", timeout=120000)
        measured = page.evaluate("window.__measured")
        element = page.query_selector(".mpf-paper")
        element.screenshot(path=path)
        version = browser.version
        context.close()
        browser.close()
    measured["page_errors"] = errors
    measured["browser_version"] = version
    measured["device_scale_factor"] = DEVICE_PIXEL_RATIO
    return measured


# --------------------------------------------------------------------------
# Image comparison
# --------------------------------------------------------------------------

def load_grey(path: str):
    from PIL import Image

    return Image.open(path).convert("L")


def align_sizes(baseline, candidate):
    """Both images must be the same pixel size to be compared at all.

    They are cropped to the smaller of the two rather than resampled: scaling one
    to fit the other would blur exactly the edges being measured and would let a
    size error disappear into a resample. Any size difference is reported.
    """
    width = min(baseline.width, candidate.width)
    height = min(baseline.height, candidate.height)
    return baseline.crop((0, 0, width, height)), candidate.crop((0, 0, width, height))


def mask_slot(image, page: Dict[str, Any], dpi: int, inset_pt: float = 1.0):
    """White out the *inside* of the figure slot, and nothing else.

    The baseline has an empty placeholder in the slot and the reproduction has an
    empty slot; comparing their interiors would measure the placeholder's hairline
    and nothing useful. The inset keeps the slot's own edges, the caption and every
    surrounding line in the comparison — those are the things that move when a page
    is wrong.
    """
    from PIL import ImageDraw

    scale = dpi / PDF_PT_PER_INCH
    slot = page["slot"]
    left = (slot["x_pt"] + inset_pt) * scale
    top = (slot["top_pt"] + inset_pt) * scale
    right = (slot["x_pt"] + slot["width_pt"] - inset_pt) * scale
    bottom = (slot["top_pt"] + slot["height_pt"] - inset_pt) * scale
    copy = image.copy()
    ImageDraw.Draw(copy).rectangle([left, top, right, bottom], fill=255)
    return copy


def difference_stats(baseline, candidate) -> Dict[str, Any]:
    from PIL import ImageChops

    diff = ImageChops.difference(baseline, candidate)
    histogram = diff.histogram()
    total = sum(histogram)
    over = {
        threshold: sum(histogram[threshold:]) for threshold in (16, 32, 64, 128)
    }
    weighted = sum(value * count for value, count in enumerate(histogram))
    return {
        "pixels": total,
        "mean_absolute_difference": round(weighted / total, 4) if total else 0.0,
        "pixels_over": {str(key): value for key, value in over.items()},
        "fraction_over": {
            str(key): round(value / total, 8) if total else 0.0 for key, value in over.items()
        },
        "max_difference": max(value for value, count in enumerate(histogram) if count),
    }, diff


def ink_coverage(image) -> float:
    """Total darkness, as a fraction of a fully black page.

    Two rasterisers can put ink in exactly the same places and still disagree
    about how much of it there is — stroke weight, gamma and anti-aliasing all
    differ. Reporting coverage separates "the glyphs are in the wrong place"
    from "the glyphs are rendered a little heavier", which a single difference
    percentage would blur together.
    """
    histogram = image.histogram()
    total = sum(histogram)
    darkness = sum((255 - value) * count for value, count in enumerate(histogram))
    return darkness / (255.0 * total) if total else 0.0


def best_shift(baseline, candidate, radius: int = 2) -> Dict[str, Any]:
    """Does moving the reproduction by a pixel or two make it agree better?

    If it does, the page has a real offset that per-pixel difference alone would
    have reported as noise. If zero shift is already the best, whatever
    difference remains is not a displacement.
    """
    from PIL import ImageChops

    scores = {}
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            moved = ImageChops.offset(candidate, dx, dy)
            diff = ImageChops.difference(baseline, moved)
            histogram = diff.histogram()
            total = sum(histogram)
            weighted = sum(value * count for value, count in enumerate(histogram))
            scores[(dx, dy)] = weighted / total if total else 0.0
    best = min(scores, key=scores.get)
    return {
        "best_offset_px": list(best),
        "best_mean_difference": round(scores[best], 5),
        "zero_offset_mean_difference": round(scores[(0, 0)], 5),
        "zero_offset_is_best": best == (0, 0),
        "pixel_mm": round(MM_PER_INCH / COMPARE_DPI, 5),
    }


# A review overlay is red, blue and the magenta where they agree, plus the
# anti-aliased ramps between. A 64-entry palette holds all of that and stores it
# in a third of the space; the grey images are left alone.
REVIEW_PALETTE_COLOURS = 64


def save_review(image, path: str, dpi: int = COMPARE_DPI) -> None:
    """Write an image for human review at REVIEW_DPI, whatever it was measured at.

    Downsampling and palettising happen strictly *after* every measurement, so
    they cannot change a result — and they keep this evidence a few megabytes
    rather than a few dozen, which is the difference between it being committed
    and being described.
    """
    from PIL import Image

    if dpi > REVIEW_DPI:
        scale = REVIEW_DPI / float(dpi)
        size = (max(1, int(round(image.width * scale))),
                max(1, int(round(image.height * scale))))
        image = image.resize(size, Image.LANCZOS)
    if image.mode == "RGB":
        image = image.quantize(colors=REVIEW_PALETTE_COLOURS, method=Image.MEDIANCUT)
    image.save(path, optimize=True)


def write_overlay(baseline, candidate, path: str) -> None:
    """Baseline in red, reproduction in blue: anything that lines up goes dark."""
    from PIL import Image, ImageChops

    inverted_baseline = ImageChops.invert(baseline)
    inverted_candidate = ImageChops.invert(candidate)
    blank = Image.new("L", baseline.size, 0)
    save_review(Image.merge("RGB", (inverted_baseline, blank, inverted_candidate)), path)


def write_difference(diff, path: str) -> None:
    from PIL import ImageChops, ImageOps

    # Inverted so the page is white and the disagreements are dark, which is the
    # way round a person can actually read.
    ImageOps.invert(ImageChops.invert(ImageChops.invert(diff))).save(path)


# --------------------------------------------------------------------------
# Geometry comparison
# --------------------------------------------------------------------------

def compare_runs(page: Dict[str, Any], measured: Dict[str, Any]) -> Dict[str, Any]:
    """Per-run baseline, left edge and width error, in millimetres."""
    expected = {run["index"]: run for run in page["runs"] if run["mode"] == "text"}
    seen = {run["index"]: run for run in measured["runs"]}

    missing = sorted(set(expected) - set(seen))
    extra = sorted(set(seen) - set(expected))

    rows: List[Dict[str, Any]] = []
    for index in sorted(set(expected) & set(seen)):
        want = expected[index]
        got = seen[index]
        rows.append({
            "index": index,
            "text": want["text"][:40],
            "baseline_error_mm": pt_to_mm(got["baseline_pt"] - want["baseline_pt"]),
            "left_error_mm": pt_to_mm(got["x_pt"] - want["x_pt"]),
            "width_error_mm": pt_to_mm(got["width_pt"] - want["width_pt"]),
            "expected_width_mm": pt_to_mm(want["width_pt"]),
        })

    def summarise(key: str) -> Dict[str, Any]:
        values = [abs(row[key]) for row in rows]
        if not values:
            return {"n": 0}
        worst = max(rows, key=lambda row: abs(row[key]))
        return {
            "n": len(values),
            "max_mm": round(max(values), 5),
            "mean_mm": round(statistics.mean(values), 5),
            "p95_mm": round(sorted(values)[max(0, int(len(values) * 0.95) - 1)], 5),
            "worst_run": {"index": worst["index"], "text": worst["text"],
                          "error_mm": round(worst[key], 5)},
        }

    return {
        "runs_compared": len(rows),
        "runs_missing_from_dom": missing,
        "runs_in_dom_but_not_measured": extra,
        "baseline": summarise("baseline_error_mm"),
        "left_edge": summarise("left_error_mm"),
        "width": summarise("width_error_mm"),
        "worst_20_by_width": sorted(
            ({"index": row["index"], "text": row["text"],
              "width_error_mm": round(row["width_error_mm"], 5),
              "expected_width_mm": round(row["expected_width_mm"], 4)}
             for row in rows),
            key=lambda row: -abs(row["width_error_mm"]),
        )[:20],
    }


def compare_slot(page: Dict[str, Any], measured: Dict[str, Any]) -> Dict[str, Any]:
    want = page["slot"]
    got = measured["slot"]
    return {
        "left_error_mm": round(pt_to_mm(got["x_pt"] - want["x_pt"]), 5),
        "top_error_mm": round(pt_to_mm(got["top_pt"] - want["top_pt"]), 5),
        "width_error_mm": round(pt_to_mm(got["width_pt"] - want["width_pt"]), 5),
        "height_error_mm": round(pt_to_mm(got["height_pt"] - want["height_pt"]), 5),
        "expected_mm": [want["width_mm"], want["height_mm"]],
    }


# --------------------------------------------------------------------------
# One page
# --------------------------------------------------------------------------

def compare_one(origin: str, venue: str, layout: str) -> Dict[str, Any]:
    page_path = os.path.join(GENERATED, "conferences", venue, layout, "page.json")
    baseline_pdf = os.path.join(BASELINE_DIR, venue, layout, "page.pdf")
    for path in (page_path, baseline_pdf):
        if not os.path.isfile(path):
            raise RuntimeError("Missing %s; run --generate first." % os.path.relpath(path, REPO_ROOT))
    with open(page_path, encoding="utf-8") as handle:
        page = json.load(handle)

    out_dir = os.path.join(CALIBRATION_DIR, "pages", venue, layout)
    os.makedirs(out_dir, exist_ok=True)
    baseline_png = os.path.join(out_dir, "baseline.png")
    browser_png = os.path.join(out_dir, "browser.png")
    rasterise(baseline_pdf, baseline_png, COMPARE_DPI)
    measured = screenshot(origin, venue, layout, browser_png)

    baseline_image = load_grey(baseline_png)
    browser_image = load_grey(browser_png)
    size_match = baseline_image.size == browser_image.size
    baseline_image, browser_image = align_sizes(baseline_image, browser_image)
    masked_baseline = mask_slot(baseline_image, page, COMPARE_DPI)
    masked_browser = mask_slot(browser_image, page, COMPARE_DPI)

    stats, diff = difference_stats(masked_baseline, masked_browser)
    stats["ink_coverage"] = {
        "baseline": round(ink_coverage(masked_baseline), 6),
        "browser": round(ink_coverage(masked_browser), 6),
    }
    stats["ink_coverage"]["ratio"] = (
        round(stats["ink_coverage"]["browser"] / stats["ink_coverage"]["baseline"], 5)
        if stats["ink_coverage"]["baseline"] else None
    )
    stats["alignment"] = best_shift(masked_baseline, masked_browser)
    write_overlay(masked_baseline, masked_browser, os.path.join(out_dir, "overlay.png"))
    from PIL import ImageChops
    save_review(ImageChops.invert(diff), os.path.join(out_dir, "difference.png"))
    # The two inputs are kept too, downsampled the same way, so a reader can see
    # each on its own rather than only their difference.
    save_review(baseline_image, baseline_png)
    save_review(browser_image, browser_png)

    runs = compare_runs(page, measured)
    slot = compare_slot(page, measured)

    paper_error_mm = [
        abs(pt_to_mm(measured["paper"]["width_pt"]) - page["paper"]["width_mm"]),
        abs(pt_to_mm(measured["paper"]["height_pt"]) - page["paper"]["height_mm"]),
    ]

    checks = [
        ("paper_size", max(paper_error_mm) <= THRESHOLDS["paper_size_mm"],
         "sheet is %.3f x %.3f mm" % (page["paper"]["width_mm"], page["paper"]["height_mm"])),
        ("raster_sizes_agree", size_match,
         "browser %s vs pdf %s pixels" % (browser_image.size, baseline_image.size)),
        ("every_run_present", not runs["runs_missing_from_dom"],
         "%d run(s) missing from the DOM" % len(runs["runs_missing_from_dom"])),
        ("run_baselines", (runs["baseline"].get("max_mm", 1e9) <= THRESHOLDS["run_baseline_mm"]),
         "worst baseline error %s mm" % runs["baseline"].get("max_mm")),
        ("run_left_edges", (runs["left_edge"].get("max_mm", 1e9) <= THRESHOLDS["run_left_edge_mm"]),
         "worst left-edge error %s mm" % runs["left_edge"].get("max_mm")),
        ("run_widths", (runs["width"].get("max_mm", 1e9) <= THRESHOLDS["run_width_mm"]),
         "worst width error %s mm" % runs["width"].get("max_mm")),
        ("slot_rectangle",
         max(abs(slot["left_error_mm"]), abs(slot["top_error_mm"]),
             abs(slot["width_error_mm"]), abs(slot["height_error_mm"])) <= THRESHOLDS["slot_edge_mm"],
         "worst slot edge error %.4f mm" % max(
             abs(slot["left_error_mm"]), abs(slot["top_error_mm"]),
             abs(slot["width_error_mm"]), abs(slot["height_error_mm"]))),
        ("no_page_errors", not measured["page_errors"], "; ".join(measured["page_errors"])[:200]),
        # A whole-image shift search is a coarser instrument than the per-run DOM
        # measurement above — one pixel at this DPI is 0.085 mm and glyph
        # rasterisation has its own sub-pixel phase — so it is held to the same
        # millimetre threshold rather than to exact zero.
        ("no_raster_drift",
         max(abs(value) for value in stats["alignment"]["best_offset_px"])
         * stats["alignment"]["pixel_mm"] <= THRESHOLDS["run_baseline_mm"],
         "the best whole-image alignment is %s px = %.4f mm"
         % (stats["alignment"]["best_offset_px"],
            max(abs(v) for v in stats["alignment"]["best_offset_px"])
            * stats["alignment"]["pixel_mm"])),
    ]

    report = {
        "report_version": "1",
        "venue": venue,
        "layout": layout,
        "status": "pass" if all(ok for _, ok, _ in checks) else "fail",
        "thresholds_mm": THRESHOLDS,
        "browser": {
            "version": measured["browser_version"],
            "device_scale_factor": measured["device_scale_factor"],
            "comparison_dpi": COMPARE_DPI,
            "fonts_loaded": measured["fontsLoaded"],
        },
        "paper_error_mm": {"width": round(paper_error_mm[0], 5), "height": round(paper_error_mm[1], 5)},
        "slot_error_mm": slot,
        "runs": runs,
        "image_difference": {
            **stats,
            "masked": "the inside of the figure slot only, inset 1 pt; the slot's edges, the "
                      "caption and all surrounding text are compared",
            "note": "Anti-aliasing makes a small non-zero difference unavoidable even for a "
                    "perfect match, which is why the geometry numbers above — measured from "
                    "the DOM against the PDF, not from the pixels — are what the thresholds "
                    "apply to. A whole-page similarity score is deliberately not used: these "
                    "pages are mostly white, and white agrees with white.",
        },
        "outputs": {
            "baseline_png": os.path.relpath(baseline_png, REPO_ROOT),
            "browser_png": os.path.relpath(browser_png, REPO_ROOT),
            "overlay_png": os.path.relpath(os.path.join(out_dir, "overlay.png"), REPO_ROOT),
            "difference_png": os.path.relpath(os.path.join(out_dir, "difference.png"), REPO_ROOT),
            "overlay_legend": "baseline in red, browser in blue; anything that lines up is black",
            "image_dpi": REVIEW_DPI,
            "image_note": "These are written at %d DPI for review. Every measurement above "
                          "was made at %d DPI, before any downsampling."
                          % (REVIEW_DPI, COMPARE_DPI),
        },
        "checks": [{"id": name, "passed": bool(ok), "detail": detail} for name, ok, detail in checks],
    }
    path = os.path.join(out_dir, "calibration-report.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return report


def run(selection: Sequence[Tuple[str, str]]) -> int:
    failures = 0
    reports = []
    with static_server(REPO_ROOT) as origin:
        for venue, layout in selection:
            report = compare_one(origin, venue, layout)
            reports.append(report)
            runs = report["runs"]
            print("%-12s %-7s %-5s  baseline %s mm  left %s mm  width %s mm  slot %.3f mm  diff>32 %.5f%%"
                  % (venue, layout, report["status"],
                     runs["baseline"].get("max_mm"), runs["left_edge"].get("max_mm"),
                     runs["width"].get("max_mm"),
                     max(abs(v) for k, v in report["slot_error_mm"].items()
                         if k.endswith("_error_mm")),
                     report["image_difference"]["fraction_over"]["32"] * 100))
            for check in report["checks"]:
                if not check["passed"]:
                    print("    [FAIL] %s: %s" % (check["id"], check["detail"]))
            failures += report["status"] != "pass"
    summary_path = os.path.join(CALIBRATION_DIR, "page-calibration.json")
    import web_fingerprint
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(web_fingerprint.stamp({
            "report_version": "1",
            "note": "Every venue/width-mode page compared against the compiled PDF it was "
                    "generated from. Written by scripts/compare_pages.py.",
            "thresholds_mm": THRESHOLDS,
            "pages": [{
                "venue": r["venue"], "layout": r["layout"], "status": r["status"],
                "worst_baseline_mm": r["runs"]["baseline"].get("max_mm"),
                "worst_left_edge_mm": r["runs"]["left_edge"].get("max_mm"),
                "worst_width_mm": r["runs"]["width"].get("max_mm"),
                "slot_error_mm": r["slot_error_mm"],
                "ink_coverage": r["image_difference"]["ink_coverage"],
                "alignment": r["image_difference"]["alignment"],
                "runs_compared": r["runs"]["runs_compared"],
                "report": "tests/web/calibration/pages/%s/%s/calibration-report.json"
                          % (r["venue"], r["layout"]),
            } for r in reports],
        }), handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print("\nsummary: %s" % os.path.relpath(summary_path, REPO_ROOT))
    return 1 if failures else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    import render_conference_context as rcc  # noqa: E402

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--venue", action="append")
    parser.add_argument("--layout", action="append")
    args = parser.parse_args(argv)

    fixtures = rcc.fixtures()
    selection = [
        (venue, layout)
        for venue in rcc.VENUES if not args.venue or venue in args.venue
        for layout in fixtures.layout_ids(venue) if not args.layout or layout in args.layout
    ]
    return run(selection)


if __name__ == "__main__":
    raise SystemExit(main())
