#!/usr/bin/env python3
"""Generate the six paper-page baselines, and check the HTML page against them.

Two jobs, one file, because they are two halves of the same claim.

**Generate** (``--generate``). For each of the three venues in each of its two
width modes, compile the venue's own template with a clean placeholder box in
the figure slot, keep the body page it lands on, and read the result apart:
paper box, text block, column positions, the slot rectangle, every text run with
its baseline and the face it is set in, the rules, and outlines for the maths
glyphs no web font can supply. That becomes ``page.json`` — the thing the HTML
paper page is *generated from*, so the browser is never guessing what LaTeX did.

**Compare** (``--compare``). Screenshot the HTML page in headless Chromium at
the same resolution as a raster of the baseline PDF, and report the difference:
per-line baseline and left-edge error in millimetres, the slot rectangle's error,
an overlay, and a difference image. Nothing is normalised away and no threshold
is relaxed to make a page pass; the numbers are written down whatever they say.

    python scripts/calibrate_conference_pages.py --generate
    python scripts/calibrate_conference_pages.py --compare
    python scripts/calibrate_conference_pages.py --generate --compare --venue icml2026

Needs LaTeX and poppler (as the context evaluation does) for ``--generate``, and
Chromium via Playwright for ``--compare``. Neither is needed by anyone *using*
the published site.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
SKILL_SCRIPTS = os.path.join(REPO_ROOT, "skills", "scientific-figures", "scripts")
TESTS_DIR = os.path.join(REPO_ROOT, "tests")
TESTS_WEB = os.path.join(TESTS_DIR, "web")

for path in (SKILL_SCRIPTS, SCRIPTS_DIR, TESTS_DIR, TESTS_WEB):
    if path not in sys.path:
        sys.path.insert(0, path)

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import evaluate_context  # noqa: E402
import figure_core  # noqa: E402
import pdf_layout  # noqa: E402
import render_conference_context as rcc  # noqa: E402

GENERATED = os.path.join(REPO_ROOT, "web", "public", "generated")
CONFERENCES_OUT = os.path.join(GENERATED, "conferences")
FONTS_MANIFEST = os.path.join(GENERATED, "fonts", "fonts.json")
CALIBRATION_DIR = os.path.join(TESTS_WEB, "calibration")
BASELINE_DIR = os.path.join(CALIBRATION_DIR, "baselines")

# The comparison resolution. High enough that a 0.1 mm error is several pixels
# (at 300 DPI one pixel is 0.085 mm), low enough that a full page is a
# manageable image.
COMPARE_DPI = 300

MM_PER_INCH = 25.4
PDF_PT_PER_INCH = 72.0


def mm(value_pt: float) -> float:
    return value_pt / PDF_PT_PER_INCH * MM_PER_INCH


class CalibrationError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# The placeholder figure
# --------------------------------------------------------------------------

def placeholder_figure(width_mm: float, height_mm: float, directory: str) -> str:
    """A blank, exactly-sized figure to occupy the slot in the baseline page.

    The baseline exists to measure a page whose figure area is *empty*: a page
    built around an old render would carry that render's ink into every
    comparison, and painting a white box over it afterwards would hide whatever
    it had pushed out of place. So the slot is filled by a real PDF of exactly
    the right size, placed through the same ``\\includegraphics`` path as a real
    figure, drawing nothing but a hairline edge so a person can see where it is.
    """
    import matplotlib.pyplot as plt

    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "figure.pdf")
    width_in = width_mm / MM_PER_INCH
    height_in = height_mm / MM_PER_INCH
    figure = plt.figure(figsize=(width_in, height_in), facecolor="white")
    axes = figure.add_axes([0, 0, 1, 1])
    axes.set_facecolor("white")
    axes.set_xticks([])
    axes.set_yticks([])
    for spine in axes.spines.values():
        spine.set_linewidth(0.4)
        spine.set_color("#B8B8B8")
    figure.savefig(path, format="pdf")
    plt.close(figure)
    return path


# --------------------------------------------------------------------------
# Reading the compiled page
# --------------------------------------------------------------------------

def packaged_faces() -> Dict[str, Dict[str, Any]]:
    if not os.path.isfile(FONTS_MANIFEST):
        raise CalibrationError(
            "No %s. Run scripts/build_fonts.py first: the page cannot be described "
            "without knowing which faces the browser will have."
            % os.path.relpath(FONTS_MANIFEST, REPO_ROOT)
        )
    with open(FONTS_MANIFEST, encoding="utf-8") as handle:
        return json.load(handle)["faces"]


def embedded_type1(pdf_path: str, families: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Open the Type 1 programs the PDF embeds for ``families``.

    Two things come out of them. The *encoding*: Computer Modern carries its
    encoding inside the font program rather than in a PDF ``/Differences`` array,
    so a byte code only becomes a glyph name once the program is parsed. And the
    *outlines*, which is the point — the maths on these pages has no equivalent
    web font, so the exact contours are taken from the very font this page was
    set with rather than approximated by a different italic.
    """
    from fontTools.t1Lib import T1Font
    from pypdf import PdfReader

    wanted = set(families)
    if not wanted:
        return {}
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    resources = page.get("/Resources").get_object().get("/Font")
    resources = resources.get_object() if resources is not None else {}

    tail = b"\n" + (b"0" * 64 + b"\n") * 8 + b"cleartomark\n"
    found: Dict[str, Dict[str, Any]] = {}
    workdir = tempfile.mkdtemp(prefix="mpf-t1-")
    try:
        for entry in resources.values():
            obj = entry.get_object()
            family = str(obj.get("/BaseFont", "")).lstrip("/").split("+", 1)[-1]
            if family not in wanted or family in found:
                continue
            descriptor = obj.get("/FontDescriptor")
            descriptor = descriptor.get_object() if descriptor is not None else {}
            program = descriptor.get("/FontFile")
            if program is None:
                raise CalibrationError(
                    "%s is used on the page but its font program is not embedded, so its "
                    "glyphs cannot be reproduced exactly. The page would have to be "
                    "recompiled with font embedding on." % family
                )
            raw = program.get_object().get_data()
            path = os.path.join(workdir, "%s.pfa" % family.replace("/", "_"))
            with open(path, "wb") as handle:
                handle.write(raw)
                if b"cleartomark" not in raw[-4096:]:
                    handle.write(tail)
            font = T1Font(path)
            font.parse()
            encoding = font.font.get("Encoding") or []
            found[family] = {
                "glyph_set": font.getGlyphSet(),
                "encoding": list(encoding),
                "units_per_em": round(1.0 / float(font.font["FontMatrix"][0])),
                "font_name": font.font.get("FontName"),
            }
        return found
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def outline_for(programs: Dict[str, Dict[str, Any]], family: str, glyph: str) -> Dict[str, Any]:
    from fontTools.pens.svgPathPen import SVGPathPen

    program = programs.get(family)
    if program is None:
        raise CalibrationError("No embedded program was read for %s." % family)
    glyph_set = program["glyph_set"]
    if glyph not in glyph_set:
        raise CalibrationError(
            "The embedded %s has no glyph %r, so the page cannot be reproduced without "
            "inventing one." % (family, glyph)
        )
    outline = glyph_set[glyph]
    pen = SVGPathPen(glyph_set)
    outline.draw(pen)
    return {
        "font": family,
        "glyph": glyph,
        "path": pen.getCommands(),
        "advance": outline.width,
        "units_per_em": program["units_per_em"],
        "source": "the Type 1 program embedded in the baseline PDF",
    }


def classify_runs(
    described: Dict[str, Any],
    faces: Dict[str, Dict[str, Any]],
    programs: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Turn raw PDF runs into what the page needs to draw them.

    A run set in a face the site packages becomes real text at a measured
    position. A run set in anything else — the Computer Modern maths — becomes a
    list of glyphs, each with its own position and its own outline, because there
    is no honest way to ask a browser for a font it does not have.
    """
    runs: List[Dict[str, Any]] = []
    outlines: Dict[str, Dict[str, Any]] = {}

    for index, run in enumerate(described["runs"]):
        family = run["font_family"]
        face = faces.get(family)
        record = {
            "index": index,
            "text": run["text"],
            "x_pt": round(run["x_pt"], 5),
            "baseline_pt": round(run["y_pt"], 5),
            "end_x_pt": round(run["end_x_pt"], 5),
            "width_pt": round(run["width_pt"], 5),
            "size_pt": round(run["size_pt"], 5),
            "pdf_font": family,
            "weight": run["weight"],
            "style": run["style"],
        }
        if face is not None:
            record["mode"] = "text"
            record["css_family"] = face["css_family"]
            # The PDF font's own name decides the face. A regular run must not be
            # drawn in the bold face and thickened by the browser, and a bold run
            # must not be a synthesised regular: both are what the calibration is
            # there to catch, so both are settled here from the embedded font.
            record["weight"] = face["weight"]
            record["style"] = face["style"]
        else:
            record["mode"] = "outline"
            program = programs.get(family, {})
            encoding = program.get("encoding") or []
            glyphs = []
            cursor = run["x_pt"]
            # Each glyph gets its own position: an outline cannot rely on a
            # browser advancing the pen for it, and the advances come from the
            # PDF's own /Widths so the run ends where the PDF says it ends.
            for code, width_1000 in zip(run["codes"], run.get("glyph_widths") or []):
                name = None
                if code < len(encoding) and encoding[code] not in (None, ".notdef", ""):
                    name = encoding[code]
                if name is None:
                    raise CalibrationError(
                        "Byte %d in a %s run maps to no glyph in the font's own encoding, "
                        "so it cannot be drawn." % (code, family)
                    )
                advance = width_1000 / 1000.0 * run["size_pt"]
                key = "%s/%s" % (family, name)
                if key not in outlines:
                    outlines[key] = outline_for(programs, family, name)
                glyphs.append({
                    "glyph": name,
                    "key": key,
                    "x_pt": round(cursor, 5),
                    "advance_pt": round(advance, 5),
                })
                cursor += advance
            record["glyphs"] = glyphs
            record["text"] = "".join(glyph["glyph"] for glyph in glyphs)
        runs.append(record)
    return runs, outlines


def text_runs_with_glyphs(pdf_path: str) -> Dict[str, Any]:
    """``pdf_layout.describe_page`` plus the per-code advance behind each run."""
    from pypdf import PdfReader

    described = pdf_layout.describe_page(pdf_path)
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    fonts = pdf_layout.page_fonts(page)
    for run in described["runs"]:
        font = fonts.get(run["font"])
        if font is None:
            continue
        run["glyph_widths"] = [font.width(code) for code in run["codes"]]
    return described


def text_block(template: Dict[str, Any], paper_height_pt: float) -> Dict[str, Any]:
    """Where the template puts its text block, from the template's own lengths."""
    margins = template.get("margins_tex_pt") or {}

    def tex_mm(key: str) -> float:
        value = margins.get(key)
        return evaluate_context.tex_pt_to_mm(value) if value is not None else 0.0

    inch_mm = MM_PER_INCH
    left_mm = inch_mm + tex_mm("oddsidemargin")
    top_mm = inch_mm + tex_mm("topmargin") + tex_mm("headheight") + tex_mm("headsep")
    return {
        "left_mm": round(left_mm, 4),
        "top_mm": round(top_mm, 4),
        "width_mm": template["textwidth_mm"],
        "height_mm": template["textheight_mm"],
        "right_mm": round(left_mm + template["textwidth_mm"], 4),
        "bottom_mm": round(top_mm + template["textheight_mm"], 4),
        "column_width_mm": template["columnwidth_mm"],
        "column_gap_mm": template["columnsep_mm"],
        "columns": template["columns"],
        "derivation": "one inch from the sheet's top-left corner, plus the template's own "
                      "oddsidemargin / topmargin + headheight + headsep, all measured by "
                      "TeX in the document",
    }


def group_blocks(runs: List[Dict[str, Any]], block: Dict[str, Any],
                 paper_height_pt: float) -> List[Dict[str, Any]]:
    """Group runs into columns and paragraph-ish blocks for a readable DOM.

    This grouping is presentational only: every run keeps its own measured
    position and nothing is laid out by it. It exists so that selecting text on
    the page yields prose in reading order rather than a jumble, which per-run
    absolute positioning alone would not give.
    """
    top_pt = (block["top_mm"] / MM_PER_INCH) * PDF_PT_PER_INCH
    bottom_pt = (block["bottom_mm"] / MM_PER_INCH) * PDF_PT_PER_INCH
    columns = int(block["columns"])
    column_left_pt = (block["left_mm"] / MM_PER_INCH) * PDF_PT_PER_INCH
    column_width_pt = (block["column_width_mm"] / MM_PER_INCH) * PDF_PT_PER_INCH
    gap_pt = (block["column_gap_mm"] / MM_PER_INCH) * PDF_PT_PER_INCH

    def region(run: Dict[str, Any]) -> str:
        top_of_text = paper_height_pt - top_pt
        bottom_of_text = paper_height_pt - bottom_pt
        if run["baseline_pt"] > top_of_text:
            return "header"
        if run["baseline_pt"] < bottom_of_text:
            return "footer"
        return "body"

    def column_of(run: Dict[str, Any]) -> int:
        if columns < 2:
            return 0
        second_left = column_left_pt + column_width_pt + gap_pt
        return 1 if run["x_pt"] >= second_left - 2.0 else 0

    for run in runs:
        run["region"] = region(run)
        run["column"] = column_of(run)

    ordered = sorted(runs, key=lambda r: (
        {"header": 0, "body": 1, "footer": 2}[r["region"]],
        r["column"],
        -r["baseline_pt"],
        r["x_pt"],
    ))

    # Lines first: runs sharing a baseline within the same column.
    lines: List[Dict[str, Any]] = []
    for run in ordered:
        if (lines and lines[-1]["region"] == run["region"]
                and lines[-1]["column"] == run["column"]
                and abs(lines[-1]["baseline_pt"] - run["baseline_pt"]) <= 0.6):
            lines[-1]["runs"].append(run["index"])
            lines[-1]["_baselines"].append(run["baseline_pt"])
            lines[-1]["x_pt"] = min(lines[-1]["x_pt"], run["x_pt"])
            lines[-1]["end_x_pt"] = max(lines[-1]["end_x_pt"], run["end_x_pt"])
            lines[-1]["text"] += run["text"]
        else:
            lines.append({
                "region": run["region"],
                "column": run["column"],
                "baseline_pt": run["baseline_pt"],
                "_baselines": [run["baseline_pt"]],
                "x_pt": run["x_pt"],
                "end_x_pt": run["end_x_pt"],
                "text": run["text"],
                "runs": [run["index"]],
            })
    for line in lines:
        line["baseline_pt"] = round(sum(line["_baselines"]) / len(line["_baselines"]), 5)
        del line["_baselines"]
        line["width_pt"] = round(line["end_x_pt"] - line["x_pt"], 5)

    # Then blocks: consecutive lines in one column, split where the vertical gap
    # grows or where a line is indented like a fresh paragraph.
    body_gaps = [
        round(previous["baseline_pt"] - current["baseline_pt"], 3)
        for previous, current in zip(lines, lines[1:])
        if previous["region"] == current["region"] == "body"
        and previous["column"] == current["column"]
        and 0 < previous["baseline_pt"] - current["baseline_pt"] < 40
    ]
    leading = statistics.median(body_gaps) if body_gaps else 12.0

    blocks: List[Dict[str, Any]] = []
    for line in lines:
        start_new = True
        if blocks:
            last = blocks[-1]
            previous = last["_last"]
            gap = previous["baseline_pt"] - line["baseline_pt"]
            same_flow = (last["region"] == line["region"] and last["column"] == line["column"])
            start_new = not (same_flow and 0 < gap <= leading * 1.35
                             and abs(line["x_pt"] - last["x_pt"]) < 0.6)
        if start_new:
            blocks.append({
                "region": line["region"],
                "column": line["column"],
                "x_pt": line["x_pt"],
                "lines": [line],
                "_last": line,
            })
        else:
            blocks[-1]["lines"].append(line)
            blocks[-1]["_last"] = line
    for entry in blocks:
        del entry["_last"]
        entry["text"] = " ".join(line["text"] for line in entry["lines"])
        entry["kind"] = (
            "header" if entry["region"] == "header"
            else "folio" if entry["region"] == "footer"
            else "caption" if entry["lines"][0]["text"].startswith("Figure")
            else "paragraph"
        )
    return blocks


# --------------------------------------------------------------------------
# Generating one baseline
# --------------------------------------------------------------------------

def generate(venue_id: str, layout_id: str, profile_path: str, timeout: int) -> Dict[str, Any]:
    fixtures = rcc.fixtures()
    venue = fixtures.venue(venue_id)
    layout = fixtures.layout(venue_id, layout_id)

    template = evaluate_context.probe_template(fixtures, venue_id, layout_id, timeout)
    profile = figure_core.load_profile(profile_path)
    aspect = float(profile["canvas"]["aspect_ratio"])
    width_mm = template["target_width_mm"]
    height_mm = width_mm * aspect

    output_dir = os.path.join(BASELINE_DIR, venue_id, layout_id)
    os.makedirs(output_dir, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="mpf-baseline-") as workdir:
        placeholder_figure(width_mm, height_mm, workdir)
        report = evaluate_context.evaluate(
            fixtures=fixtures,
            venue_id=venue_id,
            layout_id=layout_id,
            case_id="baseline",
            output_dir=output_dir,
            figure_dir=workdir,
            # One caption, identical across all six baselines, and true of both
            # the empty baseline page and the live tool that reuses this page:
            # the slot is the slot either way. A caption that described the
            # placeholder would read as a lie once a figure was in it.
            caption=evaluate_context.escape_tex(
                "Synthetic evaluation fixture, not a result. The panel above occupies "
                "exactly the width this template gives a figure in this mode, so its type "
                "prints at the size it is drawn at. The surrounding prose is an excerpt "
                "reproduced as typographic context; this page is not a paper and not a "
                "submission."
            ),
            png_dpi=150,
            timeout=timeout,
        )

    page_pdf = os.path.join(output_dir, "page.pdf")
    described = text_runs_with_glyphs(page_pdf)
    faces = packaged_faces()
    unpackaged = sorted({
        run["font_family"] for run in described["runs"] if run["font_family"] not in faces
    })
    programs = embedded_type1(page_pdf, unpackaged)
    runs, outlines = classify_runs(described, faces, programs)

    block = text_block(template, described["height_pt"])
    blocks = group_blocks(runs, block, described["height_pt"])

    forms = described["forms"]
    if len(forms) != 1:
        raise CalibrationError(
            "Expected exactly one placed form (the figure slot) on the %s %s baseline "
            "page, found %d." % (venue_id, layout_id, len(forms))
        )
    slot = forms[0]

    page = {
        "schema_version": "1",
        "note": "Generated by scripts/calibrate_conference_pages.py from a compiled "
                "LaTeX page. Every position here was measured; none was chosen. Do not "
                "edit by hand — regenerate.",
        "venue": {
            "id": venue["id"], "name": venue["name"], "year": venue["year"],
            "mode": venue["mode"], "mode_syntax": venue["mode_syntax"],
            "columns": venue["columns"],
        },
        "layout": {
            "id": layout["id"], "label": layout["label"],
            "float_environment": layout["float_environment"],
            "target_width_rule": layout["target_width_rule"],
            "target_width_factor": layout["target_width_factor"],
            "note": layout["note"],
        },
        "paper": {
            "width_pt": described["width_pt"], "height_pt": described["height_pt"],
            "width_mm": described["width_mm"], "height_mm": described["height_mm"],
            "mediabox_pt": described["mediabox_pt"],
        },
        "template": template,
        "text_block": block,
        "slot": {
            "x_pt": round(slot["x_pt"], 5),
            "y_pt": round(slot["y_pt"], 5),
            "width_pt": round(slot["width_pt"], 5),
            "height_pt": round(slot["height_pt"], 5),
            "width_mm": round(mm(slot["width_pt"]), 4),
            "height_mm": round(mm(slot["height_pt"]), 4),
            "top_pt": round(described["height_pt"] - (slot["y_pt"] + slot["height_pt"]), 5),
            "aspect_ratio": round(slot["height_pt"] / slot["width_pt"], 6),
            "note": "Measured from the page's own drawing transform, not from the "
                    "\\includegraphics argument. The figure the tool renders must be "
                    "exactly this size; the slot never grows to fit a bigger one.",
        },
        "figure": {
            "width_mm": round(width_mm, 4),
            "height_mm": round(height_mm, 4),
            "aspect_ratio": aspect,
            "aspect_ratio_source": "profile.canvas.aspect_ratio at generation time",
        },
        "runs": runs,
        "blocks": blocks,
        "rules": [
            {
                "x_pt": round(rule["x_pt"], 5), "y_pt": round(rule["y_pt"], 5),
                "width_pt": round(rule["width_pt"], 5), "height_pt": round(rule["height_pt"], 5),
            }
            for rule in described["rules"]
        ],
        "outline_glyphs": outlines,
        "fonts": sorted({run["css_family"] for run in runs if run.get("css_family")}),
        "pdf_fonts": described["fonts"],
        "provenance": {
            "generated_by": "scripts/calibrate_conference_pages.py --generate",
            "baseline_pdf": os.path.relpath(page_pdf, REPO_ROOT),
            "baseline_pdf_sha256": evaluate_context.sha256_file(page_pdf),
            "baseline_png_dpi": 150,
            "context_report": os.path.relpath(
                os.path.join(output_dir, "context-report.json"), REPO_ROOT),
            "context_status": report["status"],
            "wrapper_sha256": report["fixtures"]["wrapper_sha256"],
            "body_sha256": report["fixtures"]["body_sha256"],
            "measure_sha256": report["fixtures"]["measure_sha256"],
            "venue_files": report["fixtures"]["venue_files"],
            "profile": os.path.relpath(profile_path, REPO_ROOT),
            "placeholder": "An empty PDF of exactly the slot size, drawn with a hairline "
                           "edge and nothing else. No previous render was reused and no "
                           "part of the page was painted over.",
        },
    }

    target_dir = os.path.join(CONFERENCES_OUT, venue_id, layout_id)
    os.makedirs(target_dir, exist_ok=True)
    with open(os.path.join(target_dir, "page.json"), "w", encoding="utf-8") as handle:
        json.dump(page, handle, indent=1, ensure_ascii=False)
        handle.write("\n")
    return page


def generate_all(selection: Sequence[Tuple[str, str]], profile_path: str,
                 timeout: int) -> Dict[str, Any]:
    index = []
    for venue_id, layout_id in selection:
        page = generate(venue_id, layout_id, profile_path, timeout)
        index.append({
            "venue": venue_id,
            "layout": layout_id,
            "name": page["venue"]["name"],
            "label": page["layout"]["label"],
            "float_environment": page["layout"]["float_environment"],
            "figure_width_mm": page["figure"]["width_mm"],
            "figure_height_mm": page["figure"]["height_mm"],
            "slot_width_mm": page["slot"]["width_mm"],
            "paper_width_mm": page["paper"]["width_mm"],
            "paper_height_mm": page["paper"]["height_mm"],
            "runs": len(page["runs"]),
            "outline_glyphs": len(page["outline_glyphs"]),
            "path": "conferences/%s/%s/page.json" % (venue_id, layout_id),
        })
        print("  %-12s %-7s %8.3f mm slot, %4d runs, %d outline glyph(s)"
              % (venue_id, layout_id, page["slot"]["width_mm"], len(page["runs"]),
                 len(page["outline_glyphs"])))
    payload = {
        "schema_version": "1",
        "note": "The venue/width-mode pages the browser tool offers. Generated; do not edit.",
        "pages": index,
    }
    os.makedirs(CONFERENCES_OUT, exist_ok=True)
    with open(os.path.join(CONFERENCES_OUT, "index.json"), "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return payload


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def selection_from(args: argparse.Namespace) -> List[Tuple[str, str]]:
    fixtures = rcc.fixtures()
    pairs = []
    for venue_id in rcc.VENUES:
        if args.venue and venue_id not in args.venue:
            continue
        for layout_id in fixtures.layout_ids(venue_id):
            if args.layout and layout_id not in args.layout:
                continue
            pairs.append((venue_id, layout_id))
    return pairs


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--generate", action="store_true", help="Compile and measure the baselines.")
    parser.add_argument("--compare", action="store_true", help="Screenshot the HTML pages and diff them.")
    parser.add_argument("--venue", action="append", help="Restrict to this venue (repeatable).")
    parser.add_argument("--layout", action="append", help="Restrict to this width mode (repeatable).")
    parser.add_argument("--profile", default=figure_core.default_profile_path(
        os.path.join(REPO_ROOT, "skills", "scientific-figures")))
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args(argv)

    if not (args.generate or args.compare):
        parser.error("nothing to do: pass --generate, --compare, or both")

    selection = selection_from(args)
    if not selection:
        print("error: that venue/layout combination is not in the matrix.", file=sys.stderr)
        return 2

    try:
        if args.generate:
            absent = evaluate_context.missing_tools()
            if absent:
                print("error: --generate needs %s." % ", ".join(sorted(absent)), file=sys.stderr)
                print(evaluate_context.INSTALL_HINT, file=sys.stderr)
                return 3
            print("generating %d baseline(s):" % len(selection))
            generate_all(selection, args.profile, args.timeout)
        if args.compare:
            import compare_pages

            return compare_pages.run(selection)
    except (CalibrationError, evaluate_context.ContextError,
            figure_core.SpecError, figure_core.ProfileError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
