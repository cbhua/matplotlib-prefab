"""A grid of line/bar panels on one fixed-size canvas, shared by CLI and web."""
from __future__ import annotations

import contextlib
import copy

import figure_core as core
import inspect_figure as inspect


def validate_spec(spec):
    if not isinstance(spec, dict):
        raise core.SpecError("grid spec must be an object")
    core._check_unknown_keys(spec, {"schema_version", "kind", "rows", "columns", "panels"}, "spec")
    if spec.get("schema_version") != "1" or spec.get("kind") != "grid":
        raise core.SpecError("grid spec needs schema_version '1' and kind 'grid'")
    for field in ("rows", "columns"):
        value = spec.get(field)
        if type(value) is not int or not 1 <= value <= 4:
            raise core.SpecError("spec.%s must be an integer from 1 to 4" % field)
    panels = spec.get("panels")
    count = spec["rows"] * spec["columns"]
    if not isinstance(panels, list) or len(panels) != count:
        raise core.SpecError("spec.panels must contain exactly %d panels in row-major order" % count)
    result = copy.deepcopy(spec)
    for index, panel in enumerate(panels):
        try:
            result["panels"][index] = core.validate_spec(panel)
        except core.SpecError as exc:
            raise core.SpecError("spec.panels[%d]: %s" % (index, exc)) from exc
    return result


@contextlib.contextmanager
def drawn_figure(spec, profile, skill_root=None):
    import matplotlib.pyplot as plt

    with core.style_context(profile):
        fig, axes = plt.subplots(spec["rows"], spec["columns"], squeeze=False,
                                 figsize=core.figure_size_inches(profile),
                                 layout=profile["layout"]["engine"])
        try:
            engine = fig.get_layout_engine()
            if engine is not None:
                pad = float(profile["layout"]["pad_pt"]) / core.PT_PER_INCH
                engine.set(w_pad=pad, h_pad=pad, wspace=0.0, hspace=0.0)
            drawn = []
            for ax, panel in zip(axes.flat, spec["panels"]):
                drawn.append(core.load_template(panel["kind"], skill_root).draw(ax, panel, profile))
                core.apply_tick_type(ax, profile)
                core.apply_legend_type(ax, profile)
            yield fig, list(axes.flat), {"kind": "grid", "rows": spec["rows"],
                                         "columns": spec["columns"], "panels": drawn}
        finally:
            plt.close(fig)


def inspect_grid(fig, axes, spec, profile, drawn, output_dir=None):
    report = inspect.Report()
    inspect.check_canvas(report, fig, profile)
    report.add("panel_count", inspect.PASS if len(axes) == len(spec["panels"]) else inspect.FAIL,
               "%d panels in a %d × %d grid." % (len(axes), spec["rows"], spec["columns"]))
    fonts = inspect.check_font_resolution(report, fig, profile)
    inspect.check_glyph_coverage(report, fig, fonts)
    inspect.check_text_within_canvas(report, fig)
    for index, (ax, panel, artists) in enumerate(zip(axes, spec["panels"], drawn["panels"])):
        start = len(report.checks)
        inspect.check_font_sizes(report, fig, ax, profile)
        inspect.check_tick_label_overlap(report, fig, ax)
        if panel["kind"] in ("line", "scatter"):
            inspect.check_line_data(report, ax, panel, artists)
        else:
            inspect.check_bar_axis(report, ax, panel)
        bounds = ax.get_position()
        fraction = min(bounds.width * spec["columns"], bounds.height * spec["rows"])
        report.add("panel_area", inspect.WARN if fraction < .25 else inspect.PASS,
                   "Plot area occupies %.1f%% of the smaller allocated cell dimension." % (fraction * 100))
        for check in report.checks[start:]:
            check["id"] = "panel_%d.%s" % (index + 1, check["id"])
    # Adjacent decorations may collide even when each panel's ticks are clear.
    renderer = inspect.figure_renderer(fig)
    boxes = [ax.get_tightbbox(renderer) for ax in axes]
    overlaps = [(i + 1, j + 1) for i, a in enumerate(boxes)
                for j, b in enumerate(boxes) if j > i and a.overlaps(b)]
    report.add("panel_overlap", inspect.WARN if overlaps else inspect.PASS,
               "Panel decorations overlap: %s" % overlaps if overlaps else "Panel decorations do not overlap.")
    if output_dir is not None:
        inspect.check_outputs(report, output_dir, profile)
        inspect.check_exported_sizes(report, output_dir, profile)
    inspect.add_visual_review_placeholder(report)
    payload = {"report_schema_version": inspect.REPORT_SCHEMA_VERSION, "kind": "grid",
               "mode": "render" if output_dir is not None else "live-only",
               "environment": inspect.environment_info(fonts), "checks": report.checks}
    payload.update(report.summary())
    return payload


def render_to_svg(spec, profile, skill_root=None, checks=False):
    spec, profile = validate_spec(spec), core.validate_profile(profile)
    width, height = core.figure_size_inches(profile)
    with drawn_figure(spec, profile, skill_root) as (fig, axes, drawn):
        svg = core.figure_to_svg(fig, profile)
        report = inspect_grid(fig, axes, spec, profile, drawn) if checks else None
    return {"svg": svg, "report": report, "drawn": drawn, "spec": spec, "profile": profile,
            "width_in": width, "height_in": height,
            "width_mm": width * core.MM_PER_INCH, "height_mm": height * core.MM_PER_INCH}
