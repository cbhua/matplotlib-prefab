"""Deterministic checks on a rendered figure, producing report.json.

What this module can honestly check is limited and stated as such:

* it measures the canvas, the exported files, font sizes, resolved fonts and
  glyph coverage exactly;
* it uses *heuristics* for text overflow and tick-label collisions, so those are
  reported as warnings, never as proof of a broken figure;
* it cannot judge whether a legend hides data, whether the colours read well in
  print, or whether the science is right. ``visual_review`` therefore always
  comes back as ``not_checked`` — only a human or an agent that actually looks
  at ``figure.png`` can close it.

Usable two ways:
  * imported by ``render.py`` with the live figure (all checks),
  * run standalone on an existing output directory (file-level checks only)::

        python inspect_figure.py --output-dir .tmp/figure-preview/line
"""

from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import figure_core  # noqa: E402

PASS = "pass"
WARN = "warn"
FAIL = "fail"
NOT_CHECKED = "not_checked"

REPORT_SCHEMA_VERSION = "1"

# Rounding to whole pixels and PDF point rounding make exact equality wrong.
SIZE_TOLERANCE_IN = 1e-6
PIXEL_TOLERANCE = 1.0
PDF_POINT_TOLERANCE = 1.0
# Text is allowed to touch the canvas edge; only real spill is worth a warning.
OVERFLOW_TOLERANCE_PX = 1.0


def figure_renderer(fig):
    """A renderer for measuring text — the same one whatever backend drew the figure.

    These checks measure text extents, and text extents depend on the renderer
    doing the measuring. The Agg canvas can hand one out; the SVG canvas the
    browser worker runs on cannot, and matplotlib's fallback for that leaves the
    figure at 72 DPI afterwards, which quietly changes every measurement taken
    after it. Either way the browser and the command line would disagree about
    whether a label overflows — the same figure, two verdicts.

    So one is built here, from Agg, at the figure's own DPI, touching nothing.
    The check then depends on the figure and not on how it happens to be being
    exported.
    """
    from matplotlib.backends.backend_agg import RendererAgg

    width_in, height_in = fig.get_size_inches()
    return RendererAgg(int(round(width_in * fig.dpi)), int(round(height_in * fig.dpi)), fig.dpi)


class Report:
    def __init__(self) -> None:
        self.checks: List[Dict[str, Any]] = []

    def add(self, check_id: str, status: str, message: str, **details: Any) -> None:
        entry: Dict[str, Any] = {"id": check_id, "status": status, "message": message}
        if details:
            entry["details"] = details
        self.checks.append(entry)

    def summary(self) -> Dict[str, Any]:
        counts = {PASS: 0, WARN: 0, FAIL: 0, NOT_CHECKED: 0}
        for check in self.checks:
            counts[check["status"]] = counts.get(check["status"], 0) + 1
        if counts[FAIL]:
            status = FAIL
        elif counts[WARN]:
            status = WARN
        else:
            status = PASS
        return {"status": status, "counts": counts}


# --------------------------------------------------------------------------
# File-level helpers (no live figure required)
# --------------------------------------------------------------------------

def png_pixel_size(path: str) -> Optional[Tuple[int, int]]:
    with open(path, "rb") as handle:
        header = handle.read(33)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", header[16:24])
    return int(width), int(height)


_MEDIABOX = re.compile(
    rb"/MediaBox\s*\[\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\]"
)


def pdf_page_size_pt(path: str) -> Optional[Tuple[float, float]]:
    """Best-effort MediaBox scan.

    Matplotlib writes the page box uncompressed, so a regex is enough and no
    heavy PDF dependency is pulled into the runtime path. Returns ``None`` when
    the box cannot be found, which is reported as ``not_checked`` rather than a
    failure.
    """
    with open(path, "rb") as handle:
        blob = handle.read()
    match = _MEDIABOX.search(blob)
    if match is None:
        return None
    x0, y0, x1, y1 = (float(value) for value in match.groups())
    return abs(x1 - x0), abs(y1 - y0)


def check_outputs(report: Report, output_dir: str, profile: Optional[Dict[str, Any]]) -> None:
    expected = []
    if profile is None or profile["output"].get("write_pdf", True):
        expected.append("figure.pdf")
    if profile is None or profile["output"].get("write_png", True):
        expected.append("figure.png")

    missing = []
    empty = []
    for name in expected:
        path = os.path.join(output_dir, name)
        if not os.path.isfile(path):
            missing.append(name)
        elif os.path.getsize(path) == 0:
            empty.append(name)
    if missing or empty:
        report.add(
            "outputs_present",
            FAIL,
            "Expected output(s) missing or empty: %s"
            % ", ".join(sorted(missing + empty)),
            missing=missing,
            empty=empty,
        )
        return
    report.add(
        "outputs_present",
        PASS,
        "All expected outputs exist and are non-empty: %s" % ", ".join(expected),
        files=expected,
    )


def check_exported_sizes(
    report: Report, output_dir: str, profile: Optional[Dict[str, Any]]
) -> None:
    if profile is None:
        report.add(
            "png_pixel_size",
            NOT_CHECKED,
            "No profile available, so the expected pixel size is unknown.",
        )
        report.add(
            "pdf_page_size",
            NOT_CHECKED,
            "No profile available, so the expected page size is unknown.",
        )
        return

    width_in, height_in = figure_core.figure_size_inches(profile)

    png_path = os.path.join(output_dir, "figure.png")
    if profile["output"].get("write_png", True) and os.path.isfile(png_path):
        size = png_pixel_size(png_path)
        if size is None:
            report.add("png_pixel_size", FAIL, "figure.png is not a readable PNG file.")
        else:
            dpi = float(profile["output"]["png_dpi"])
            expected = (round(width_in * dpi), round(height_in * dpi))
            deltas = (abs(size[0] - expected[0]), abs(size[1] - expected[1]))
            status = PASS if max(deltas) <= PIXEL_TOLERANCE else FAIL
            report.add(
                "png_pixel_size",
                status,
                "figure.png is %dx%d px; expected %dx%d px at %g DPI (tolerance %g px "
                "for rounding)." % (size[0], size[1], expected[0], expected[1], dpi, PIXEL_TOLERANCE),
                actual_px=list(size),
                expected_px=list(expected),
                dpi=dpi,
            )
    else:
        report.add("png_pixel_size", NOT_CHECKED, "No PNG was requested or found.")

    pdf_path = os.path.join(output_dir, "figure.pdf")
    if profile["output"].get("write_pdf", True) and os.path.isfile(pdf_path):
        size_pt = pdf_page_size_pt(pdf_path)
        if size_pt is None:
            report.add(
                "pdf_page_size",
                NOT_CHECKED,
                "Could not locate the PDF MediaBox with a plain scan; the page size "
                "was not verified at runtime (the test suite checks it with a PDF parser).",
            )
        else:
            expected_pt = (
                width_in * figure_core.PT_PER_INCH,
                height_in * figure_core.PT_PER_INCH,
            )
            deltas = (
                abs(size_pt[0] - expected_pt[0]),
                abs(size_pt[1] - expected_pt[1]),
            )
            status = PASS if max(deltas) <= PDF_POINT_TOLERANCE else FAIL
            report.add(
                "pdf_page_size",
                status,
                "figure.pdf page is %.2fx%.2f pt (%.2fx%.2f mm); expected %.2fx%.2f pt."
                % (
                    size_pt[0],
                    size_pt[1],
                    size_pt[0] / figure_core.PT_PER_INCH * figure_core.MM_PER_INCH,
                    size_pt[1] / figure_core.PT_PER_INCH * figure_core.MM_PER_INCH,
                    expected_pt[0],
                    expected_pt[1],
                ),
                actual_pt=[round(value, 3) for value in size_pt],
                expected_pt=[round(value, 3) for value in expected_pt],
            )
    else:
        report.add("pdf_page_size", NOT_CHECKED, "No PDF was requested or found.")


# --------------------------------------------------------------------------
# Live-figure checks
# --------------------------------------------------------------------------

def check_canvas(report: Report, fig, profile: Dict[str, Any]) -> None:
    expected = figure_core.figure_size_inches(profile)
    actual = tuple(float(value) for value in fig.get_size_inches())
    deltas = (abs(actual[0] - expected[0]), abs(actual[1] - expected[1]))
    status = PASS if max(deltas) <= SIZE_TOLERANCE_IN else FAIL
    report.add(
        "canvas_size",
        status,
        "Canvas is %.4fx%.4f in (%.2fx%.2f mm); the profile asks for %.4fx%.4f in."
        % (
            actual[0],
            actual[1],
            actual[0] * figure_core.MM_PER_INCH,
            actual[1] * figure_core.MM_PER_INCH,
            expected[0],
            expected[1],
        ),
        actual_in=[round(value, 6) for value in actual],
        expected_in=[round(value, 6) for value in expected],
        width_mm=round(actual[0] * figure_core.MM_PER_INCH, 4),
    )


def check_single_panel(report: Report, fig) -> None:
    n_axes = len(fig.axes)
    status = PASS if n_axes == 1 else FAIL
    report.add(
        "single_panel",
        status,
        "The figure holds %d axes; this skill renders exactly one panel." % n_axes,
        n_axes=n_axes,
    )


# A panel squeezed below this share of the canvas is no longer a figure worth
# exporting, whatever the individual artists say.
MIN_PANEL_FRACTION = 0.25


def check_panel_area(report: Report, fig, ax) -> None:
    fig.draw_without_rendering()
    canvas = fig.bbox
    panel = ax.get_window_extent(renderer=figure_renderer(fig))
    fractions = (panel.width / canvas.width, panel.height / canvas.height)
    if min(fractions) <= 0.0:
        status, advice = FAIL, "The plotting area collapsed to zero; nothing usable was drawn."
    elif min(fractions) < MIN_PANEL_FRACTION:
        status, advice = WARN, (
            "Labels, ticks or the legend are eating the canvas. Shorten the labels, move "
            "the legend, drop series, or raise profile.canvas.width_mm."
        )
    else:
        status, advice = PASS, "The plotting area has room for the data."
    report.add(
        "panel_area",
        status,
        "The panel occupies %.1f%% of the canvas width and %.1f%% of its height. %s"
        % (fractions[0] * 100.0, fractions[1] * 100.0, advice),
        width_fraction=round(fractions[0], 4),
        height_fraction=round(fractions[1], 4),
        min_fraction=MIN_PANEL_FRACTION,
    )


def _offscreen_tick_labels(fig) -> set:
    """Ids of tick labels whose tick sits outside the current view limits.

    A locator can generate ticks beyond the data range; matplotlib keeps their
    Text artists alive but never draws them. Checking those would produce
    phantom overflow and collision warnings, so they are excluded everywhere.
    """
    hidden = set()
    for axes in fig.axes:
        for axis in (axes.xaxis, axes.yaxis):
            low, high = sorted(axis.get_view_interval())
            span = high - low
            slack = abs(span) * 1e-9 if span else 1e-9
            for location, label in zip(axis.get_majorticklocs(), axis.get_ticklabels()):
                if not (low - slack <= location <= high + slack):
                    hidden.add(id(label))
    return hidden


def _visible_texts(fig) -> List[Any]:
    import matplotlib.text as mtext

    hidden = _offscreen_tick_labels(fig)
    texts = []
    for artist in fig.findobj(mtext.Text):
        if not artist.get_visible() or id(artist) in hidden:
            continue
        if not artist.get_text().strip():
            continue
        texts.append(artist)
    return texts


def _role_texts(fig, ax) -> List[Tuple[str, Any, str]]:
    """(role, text artist, style role) for the texts whose type the profile fixes.

    The role names are ``figure_core``'s, so x and y are asked about separately:
    a profile can now give the y label a different size from the x label, and a
    check that compared both against one shared field would pass a figure whose
    y label was ignored.
    """
    roles: List[Tuple[str, Any, str]] = []
    if ax.get_xlabel().strip():
        roles.append(("x_label", ax.xaxis.label, "x_label"))
    if ax.get_ylabel().strip():
        roles.append(("y_label", ax.yaxis.label, "y_label"))
    if ax.get_title().strip():
        roles.append(("title", ax.title, "title"))
    hidden = _offscreen_tick_labels(fig)
    for axis_role, labels in (("xtick", ax.get_xticklabels()), ("ytick", ax.get_yticklabels())):
        for label in labels:
            if label.get_text().strip() and label.get_visible() and id(label) not in hidden:
                roles.append((axis_role, label, axis_role))
    legend = ax.get_legend()
    if legend is not None:
        for text in legend.get_texts():
            roles.append(("legend", text, "legend"))
    return roles


def check_font_sizes(report: Report, fig, ax, profile: Dict[str, Any]) -> None:
    """Every text artist is the size *and weight* the resolved profile asks for.

    Weight is checked as well as size because the per-axis weight overrides are
    applied to artists rather than through rcParams, and a control whose value
    never reached the drawing would otherwise look like it worked.
    """
    mismatches = []
    checked = 0
    for role, artist, style_role in _role_texts(fig, ax):
        expected = figure_core.font_size(profile, style_role)
        expected_weight = figure_core.font_weight(profile, style_role)
        actual = float(artist.get_fontsize())
        actual_weight = artist.get_fontweight()
        checked += 1
        if abs(actual - expected) > 1e-6:
            mismatches.append({
                "role": role, "attribute": "size",
                "text": artist.get_text(),
                "actual_pt": actual, "expected_pt": expected,
            })
        if str(actual_weight) != str(expected_weight):
            mismatches.append({
                "role": role, "attribute": "weight",
                "text": artist.get_text(),
                "actual": actual_weight, "expected": expected_weight,
            })
    if not checked:
        report.add("font_sizes", NOT_CHECKED, "The figure carries no non-empty text.")
        return
    status = PASS if not mismatches else FAIL
    report.add(
        "font_sizes",
        status,
        "Checked %d text element(s) against the resolved profile (size and weight); "
        "%d mismatch(es)." % (checked, len(mismatches)),
        n_checked=checked,
        mismatches=mismatches,
        resolved_type=figure_core.resolved_type(profile),
    )


def _resolve_font(prop) -> Tuple[str, str]:
    from matplotlib import font_manager, ft2font

    path = font_manager.findfont(prop, fallback_to_default=True)
    try:
        family = ft2font.FT2Font(path).family_name
    except Exception:  # pragma: no cover - unreadable font file
        family = os.path.basename(path)
    return path, family


def check_font_resolution(report: Report, fig, profile: Dict[str, Any]) -> Dict[str, str]:
    requested = figure_core.font_family_list(profile)
    resolved: Dict[str, str] = {}
    fallbacks = []
    for artist in _visible_texts(fig):
        path, family = _resolve_font(artist.get_fontproperties())
        resolved[family] = path
        if family.lower() != requested[0].lower() and family not in requested:
            fallbacks.append({"text": artist.get_text(), "resolved_family": family})
    if not resolved:
        report.add("font_resolution", NOT_CHECKED, "The figure carries no non-empty text.")
        return {}
    if fallbacks:
        report.add(
            "font_resolution",
            WARN,
            "profile.fonts.family is %r but matplotlib resolved %d text element(s) to a "
            "different family. The requested font is probably not installed."
            % (requested[0], len(fallbacks)),
            requested=requested,
            resolved=resolved,
            fallbacks=fallbacks[:10],
        )
    else:
        report.add(
            "font_resolution",
            PASS,
            "All text resolves to the requested family %r." % requested[0],
            requested=requested,
            resolved=resolved,
        )
    return resolved


_MATH_SEGMENT = re.compile(r"(?<!\\)\$.*?(?<!\\)\$", re.DOTALL)


def check_glyph_coverage(
    report: Report, fig, resolved_fonts: Dict[str, str]
) -> None:
    from matplotlib import ft2font

    if not resolved_fonts:
        report.add("glyph_coverage", NOT_CHECKED, "The figure carries no non-empty text.")
        return

    charmaps: Dict[str, Any] = {}
    missing: List[Dict[str, Any]] = []
    mathtext_texts = 0
    for artist in _visible_texts(fig):
        text = artist.get_text()
        literal = _MATH_SEGMENT.sub("", text)
        if literal != text:
            mathtext_texts += 1
        path, _family = _resolve_font(artist.get_fontproperties())
        if path not in charmaps:
            try:
                charmaps[path] = set(ft2font.FT2Font(path).get_charmap())
            except Exception:  # pragma: no cover - unreadable font file
                charmaps[path] = None
        charmap = charmaps[path]
        if charmap is None:
            continue
        absent = sorted({ch for ch in literal if not ch.isspace() and ord(ch) not in charmap})
        if absent:
            missing.append(
                {
                    "text": text,
                    "font": os.path.basename(path),
                    "missing_characters": absent,
                    "codepoints": ["U+%04X" % ord(ch) for ch in absent],
                }
            )

    note = (
        " %d text element(s) contain mathtext; only their literal parts were checked."
        % mathtext_texts
        if mathtext_texts
        else ""
    )
    if missing:
        report.add(
            "glyph_coverage",
            FAIL,
            "%d text element(s) use characters the resolved font does not contain; they "
            "render as empty boxes. Set profile.fonts.family / fonts.fallbacks to a font "
            "that covers them (for CJK text, install and name such a font).%s"
            % (len(missing), note),
            missing=missing,
        )
    else:
        report.add(
            "glyph_coverage",
            PASS,
            "Every character in the figure exists in its resolved font.%s" % note,
        )


def check_text_within_canvas(report: Report, fig) -> None:
    fig.draw_without_rendering()
    renderer = figure_renderer(fig)
    canvas = fig.bbox
    overflowing = []
    for artist in _visible_texts(fig):
        try:
            bbox = artist.get_window_extent(renderer=renderer)
        except Exception:  # pragma: no cover - artist without an extent
            continue
        overflow = {
            "left": canvas.x0 - bbox.x0,
            "right": bbox.x1 - canvas.x1,
            "bottom": canvas.y0 - bbox.y0,
            "top": bbox.y1 - canvas.y1,
        }
        worst = max(overflow.values())
        if worst > OVERFLOW_TOLERANCE_PX:
            overflowing.append(
                {
                    "text": artist.get_text(),
                    "overflow_px": {k: round(v, 2) for k, v in overflow.items() if v > 0},
                }
            )
    if overflowing:
        report.add(
            "text_within_canvas",
            WARN,
            "%d text element(s) extend past the canvas and will be clipped in the "
            "exported files. Shorten the label, rotate tick labels, or raise "
            "profile.canvas.width_mm." % len(overflowing),
            overflowing=overflowing,
        )
    else:
        report.add("text_within_canvas", PASS, "All text fits inside the canvas.")


def check_tick_label_overlap(report: Report, fig, ax) -> None:
    fig.draw_without_rendering()
    renderer = figure_renderer(fig)
    hidden = _offscreen_tick_labels(fig)
    collisions = []
    for axis_name, labels in (
        ("x", ax.get_xticklabels()),
        ("y", ax.get_yticklabels()),
    ):
        boxes = []
        for label in labels:
            if not label.get_visible() or not label.get_text().strip():
                continue
            if id(label) in hidden:
                continue
            try:
                boxes.append((label.get_text(), label.get_window_extent(renderer=renderer)))
            except Exception:  # pragma: no cover
                continue
        for (text_a, box_a), (text_b, box_b) in zip(boxes, boxes[1:]):
            if box_a.overlaps(box_b):
                collisions.append({"axis": axis_name, "labels": [text_a, text_b]})
    if collisions:
        report.add(
            "tick_label_overlap",
            WARN,
            "%d neighbouring tick-label pair(s) overlap. This is a bounding-box "
            "heuristic: rotate the labels (profile.bar.category_label_rotation_deg), "
            "lower profile.axes.max_xticks, shorten the labels, or widen the canvas."
            % len(collisions),
            collisions=collisions,
        )
    else:
        report.add("tick_label_overlap", PASS, "No neighbouring tick labels overlap.")


def check_line_data(report: Report, ax, spec: Dict[str, Any], drawn: Dict[str, Any]) -> None:
    expected_points = len(spec["x"])
    expected_series = len(spec["series"])
    data_lines = [line for line in ax.lines if line.get_label() and not line.get_label().startswith("_")]
    problems = []
    if len(data_lines) != expected_series:
        problems.append(
            "the axes holds %d labelled line(s) but the spec has %d series"
            % (len(data_lines), expected_series)
        )
    for line, item in zip(data_lines, spec["series"]):
        n_drawn = len(line.get_xydata())
        if n_drawn != expected_points:
            problems.append(
                "series %r was drawn with %d point(s) but the spec supplies %d"
                % (item["name"], n_drawn, expected_points)
            )
        if line.get_label() != item["name"]:
            problems.append(
                "series order changed: position %d is labelled %r but the spec has %r"
                % (spec["series"].index(item), line.get_label(), item["name"])
            )
    status = PASS if not problems else FAIL
    report.add(
        "line_data_integrity",
        status,
        "Every series keeps its input order and all %d point(s)." % expected_points
        if status == PASS
        else "; ".join(problems),
        n_series=expected_series,
        n_points=expected_points,
        problems=problems,
    )

    styles = [item["style"] for item in drawn["series"]]
    keys = [(style["color"], style["linestyle"], style["marker"]) for style in styles]
    if len(set(keys)) == len(keys):
        report.add(
            "series_distinguishable",
            PASS,
            "All %d series carry a distinct colour/dash/marker combination." % len(keys),
            styles=styles,
        )
    else:
        report.add(
            "series_distinguishable",
            FAIL,
            "Two or more series share the same colour, dash pattern and marker.",
            styles=styles,
        )

    if expected_series > 1 and not drawn.get("legend_drawn"):
        report.add(
            "legend_present",
            FAIL,
            "The figure has %d series but no legend, so the series cannot be named."
            % expected_series,
        )
    else:
        report.add(
            "legend_present",
            PASS,
            "Legend drawn." if drawn.get("legend_drawn") else
            "Single series with no legend, per profile.legend.show_for_single_series.",
        )


def check_bar_axis(report: Report, ax, spec: Dict[str, Any]) -> None:
    low, high = ax.get_ylim()
    if low <= 0.0 <= high:
        report.add(
            "bar_zero_in_range",
            PASS,
            "The y range [%g, %g] contains zero, so bar lengths are comparable."
            % (low, high),
            ylim=[low, high],
        )
    else:
        report.add(
            "bar_zero_in_range",
            FAIL,
            "The y range [%g, %g] excludes zero; bar lengths would be misleading."
            % (low, high),
            ylim=[low, high],
        )

    drawn_labels = [label.get_text() for label in ax.get_xticklabels()]
    if drawn_labels == list(spec["categories"]):
        report.add(
            "bar_category_order",
            PASS,
            "Category order matches the spec exactly.",
            categories=drawn_labels,
        )
    else:
        report.add(
            "bar_category_order",
            FAIL,
            "Drawn categories %r do not match the spec order %r."
            % (drawn_labels, spec["categories"]),
            drawn=drawn_labels,
            expected=list(spec["categories"]),
        )

    n_bars = len([patch for patch in ax.patches])
    if n_bars == len(spec["values"]):
        report.add(
            "bar_count",
            PASS,
            "Drew one bar per category (%d)." % n_bars,
            n_bars=n_bars,
        )
    else:
        report.add(
            "bar_count",
            FAIL,
            "Drew %d bar(s) for %d category values." % (n_bars, len(spec["values"])),
            n_bars=n_bars,
        )


def add_visual_review_placeholder(report: Report) -> None:
    report.add(
        "visual_review",
        NOT_CHECKED,
        "Open figure.png and judge it: is every label legible at final size, does the "
        "legend sit clear of the data, are the series separable, is the panel crowded? "
        "No script can settle this, and nothing here fills it in automatically. If the "
        "environment cannot display images, record that the visual review did not happen.",
    )


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------

def environment_info(resolved_fonts: Dict[str, str]) -> Dict[str, Any]:
    import matplotlib

    return {
        "python": sys.version.split()[0],
        "matplotlib": matplotlib.__version__,
        "matplotlib_backend": matplotlib.get_backend(),
        "resolved_fonts": resolved_fonts,
    }


def _run_live_checks(report: "Report", fig, ax, spec, profile, drawn) -> Dict[str, str]:
    """Every check that needs only the live figure. Shared by both entry points.

    Split out so the browser can run exactly these — the same functions, the same
    thresholds — rather than a second, more forgiving set. The crowding and
    collision warnings are the ones that matter most while someone is moving a
    type-size slider, and a preview that stayed silent about them would be
    inviting an illegible figure.
    """
    check_canvas(report, fig, profile)
    check_single_panel(report, fig)
    check_panel_area(report, fig, ax)
    check_font_sizes(report, fig, ax, profile)
    resolved_fonts = check_font_resolution(report, fig, profile)
    check_glyph_coverage(report, fig, resolved_fonts)
    check_text_within_canvas(report, fig)
    check_tick_label_overlap(report, fig, ax)

    if spec["kind"] in ("line", "scatter"):
        check_line_data(report, ax, spec, drawn)
    else:
        check_bar_axis(report, ax, spec)
    return resolved_fonts


def inspect_live(
    fig,
    ax,
    spec: Dict[str, Any],
    profile: Dict[str, Any],
    drawn: Dict[str, Any],
) -> Dict[str, Any]:
    """The checks that do not need files on disk.

    For callers that have a figure in memory and no output directory — the
    browser worker. The file-level checks are absent rather than faked, and
    ``visual_review`` stays open here as everywhere else: an automatic render
    succeeding is not somebody looking at it.
    """
    report = Report()
    resolved_fonts = _run_live_checks(report, fig, ax, spec, profile, drawn)
    add_visual_review_placeholder(report)
    payload = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "mode": "live-only",
        "kind": spec["kind"],
        "checks_not_run": ["outputs_present", "png_pixel_size", "pdf_page_size"],
        "checks_not_run_reason": "nothing was written to disk, so there are no files to "
                                 "check. render.py runs these when it writes its five files.",
        "environment": environment_info(resolved_fonts),
        "checks": report.checks,
    }
    payload.update(report.summary())
    return payload


def inspect_render(
    fig,
    ax,
    spec: Dict[str, Any],
    profile: Dict[str, Any],
    drawn: Dict[str, Any],
    output_dir: str,
) -> Dict[str, Any]:
    """Run every check against a freshly rendered figure and its output files."""
    report = Report()

    resolved_fonts = _run_live_checks(report, fig, ax, spec, profile, drawn)

    check_outputs(report, output_dir, profile)
    check_exported_sizes(report, output_dir, profile)
    add_visual_review_placeholder(report)

    payload = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "kind": spec["kind"],
        "profile": {
            "name": profile.get("name"),
            "version": profile.get("profile_version"),
            "status": profile.get("status"),
        },
        "environment": environment_info(resolved_fonts),
        "checks": report.checks,
    }
    payload.update(report.summary())
    return payload


def inspect_output_dir(output_dir: str, profile_path: Optional[str] = None) -> Dict[str, Any]:
    """File-level re-check of an existing output directory."""
    report = Report()
    profile: Optional[Dict[str, Any]] = None
    resolved_profile = os.path.join(output_dir, "profile.resolved.json")
    source = profile_path or (resolved_profile if os.path.isfile(resolved_profile) else None)
    if source:
        profile = figure_core.load_profile(source)

    check_outputs(report, output_dir, profile)
    check_exported_sizes(report, output_dir, profile)
    add_visual_review_placeholder(report)

    payload = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "mode": "output-dir-only",
        "output_dir": os.path.abspath(output_dir),
        "profile_source": os.path.abspath(source) if source else None,
        "checks": report.checks,
    }
    payload.update(report.summary())
    return payload


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-check an existing figure output directory (file-level checks only)."
    )
    parser.add_argument("--output-dir", required=True, help="Directory holding figure.pdf / figure.png.")
    parser.add_argument(
        "--profile",
        default=None,
        help="Profile to check against. Defaults to profile.resolved.json in the output directory.",
    )
    args = parser.parse_args(argv)

    if not os.path.isdir(args.output_dir):
        print("error: no such directory: %s" % args.output_dir, file=sys.stderr)
        return 2
    payload = inspect_output_dir(args.output_dir, args.profile)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["status"] != FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
