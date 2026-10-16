"""Resolve packaged venue references and evaluate their declarative recommendations.

No LaTeX or browser is required. This evaluates physical style/width constraints,
not article placement, legend occlusion or a scientific-information score.
"""

from __future__ import annotations

import copy
import os
import re
from typing import Any, Dict, Optional, Tuple

import figure_core
from inspect_figure import Report, PASS, WARN, NOT_CHECKED


def _merge(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_preset(preset_id: str, skill_root: str) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    """Return preset, validated render profile, source path; no cwd/repo dependency."""
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", preset_id):
        raise figure_core.ProfileError("preset must be a packaged identifier, e.g. iclr2026-first.")
    path = os.path.join(skill_root, "references", "conference-presets", preset_id + ".json")
    try:
        preset = figure_core.load_json(path, "Conference preset")
    except figure_core.SpecError as exc:
        raise figure_core.ProfileError(str(exc)) from None
    if preset.get("schema_version") != "1" or preset.get("id") != preset_id:
        raise figure_core.ProfileError("Conference preset schema_version/id does not match: %s" % path)
    base = figure_core.load_profile(figure_core.default_profile_path(skill_root))
    profile = figure_core.validate_profile(_merge(base, preset["profile_overrides"]))
    return preset, profile, path


def evaluate_preset(spec: Dict[str, Any], profile: Dict[str, Any], preset: Dict[str, Any],
                    text_wrap: Optional[bool] = None) -> Report:
    """Apply context preferences once per shared role, retaining affected panels.

    Input styles have already been validated and verified on the live artists by
    inspect_figure. Bounds are inclusive. Failures here are suggestions (warn),
    not invalid-data errors. None of these checks mutate the spec or profile.
    """
    report = Report()
    panels = spec["panels"] if spec["kind"] == "grid" else [spec]
    body = preset["paper"]["body_size_pt"]
    rules = preset["rules"]

    def indices(predicate):
        return [i for i, panel in enumerate(panels) if predicate(panel)]

    def role(role_name, actual, minimum, maximum, affected, **extra):
        if not affected:
            return
        valid = minimum - 1e-9 <= actual <= maximum + 1e-9
        report.add("reference." + role_name, PASS if valid else WARN,
                   "%s: %.2f pt; recommended %.2f–%.2f pt beside %.2f pt body text."
                   % (role_name, actual, minimum, maximum, body),
                   rule_id="paper-relative-typography", actual_pt=actual,
                   minimum_pt=minimum, maximum_pt=maximum, body_pt=body,
                   body_ratio=actual / body, panel_indices=affected, **extra)

    a = rules["axis_labels"]
    t = rules["tick_labels"]
    for axis in ("x", "y"):
        label = figure_core.font_size(profile, axis + "_label")
        tick = figure_core.font_size(profile, axis + "tick")
        visible = indices(lambda p: bool(p[axis + "_label"]))
        role(axis + "_label", label, body * a["minimum_body_ratio"],
             body * a["maximum_body_ratio"], visible)
        lo, hi = body * t["minimum_body_ratio"], body * t["maximum_body_ratio"]
        rlo = label * t["target_axis_label_ratio"] - t["axis_label_tolerance_pt"]
        rhi = label * t["target_axis_label_ratio"] + t["axis_label_tolerance_pt"]
        intersect_lo, intersect_hi = max(lo, rlo), min(hi, rhi)
        deferred = bool(visible) and intersect_lo > intersect_hi
        # Without an axis title, or with disjoint intervals, only the calibrated
        # print range applies. Never recommend an impossible interval.
        relative = bool(visible) and not deferred
        affected = indices(lambda p: True) if tick < lo - 1e-9 or tick > hi + 1e-9 else (
            visible if relative else indices(lambda p: True))
        role(axis + "tick", tick, intersect_lo if relative else lo,
             intersect_hi if relative else hi, affected,
             axis_label_pt=label if visible else None,
             axis_relative_minimum_pt=rlo if visible else None,
             axis_relative_maximum_pt=rhi if visible else None,
             axis_relative_constraint_deferred=deferred)

    paired = indices(lambda p: bool(p["x_label"] and p["y_label"]))
    x, y = (figure_core.font_size(profile, axis + "_label") for axis in ("x", "y"))
    if paired:
        report.add("reference.axis_label_consistency",
                   PASS if abs(x - y) <= a["equal_size_tolerance_pt"] + 1e-9 else WARN,
                   "Use equal X/Y axis-label sizes.", rule_id="axis-label-consistency",
                   x_label_pt=x, y_label_pt=y, panel_indices=paired,
                   maximum_difference_pt=a["equal_size_tolerance_pt"])

    legends = indices(lambda p: p["kind"] != "bar" and (
        profile["legend"].get("placement", "inside") == "outside"
        or len(p["series"]) > 1 or profile["legend"]["show_for_single_series"]))
    role("legend", figure_core.font_size(profile, "legend"),
         body * rules["legend"]["minimum_body_ratio"],
         body * rules["legend"]["maximum_body_ratio"], legends)

    width = profile["canvas"]["width_mm"]
    body_width = preset["paper"]["body_width_mm"]
    wrap = preset["placement"]["text_wrap"] if text_wrap is None else text_wrap
    report.add("reference.text_width", PASS if width <= body_width + 1e-9 else WARN,
               "Compare the figure width with the available body text block.",
               figure_width_mm=width, body_width_mm=body_width)
    if wrap:
        w = rules["wrapped_figure"]
        ratio = width / body_width
        remaining = body_width - width - preset["placement"]["wrap_gap_mm"]
        narrow = ratio < w["minimum_recommended_ratio"] - 1e-9
        wide = ratio > w["maximum_recommended_ratio"] + 1e-9 or remaining < w["minimum_remaining_text_mm"]
        report.add("reference.wrapped_figure_width", WARN if narrow or wide else PASS,
                   "Wrapped figure is too narrow for its caption." if narrow else
                   "Wrapped figure leaves too little room for prose." if wide else
                   "Wrapped figure width is within the reference range.",
                   rule_id="wrapped-figure-width", figure_width_mm=width,
                   body_width_mm=body_width, body_width_ratio=ratio,
                   remaining_text_mm=remaining,
                   minimum_recommended_ratio=w["minimum_recommended_ratio"],
                   maximum_recommended_ratio=w["maximum_recommended_ratio"],
                   caption_cramped=ratio < w["caption_cramped_below_ratio"] - 1e-9)

    floor = rules["strokes"]["minimum_checked_pt"]
    roles = {"axes": profile["lines"]["axes_linewidth_pt"],
             "ticks": profile["lines"]["tick_linewidth_pt"]}
    if any(p["kind"] == "line" for p in panels):
        roles["data"] = profile["lines"]["data_linewidth_pt"]
    thin = {name: size for name, size in roles.items() if size < floor}
    report.add("reference.strokes", WARN if thin else PASS,
               "Check printed stroke visibility; there is no adopted upper-width cutoff.",
               rule_id="print-strokes", actual_pt=roles, below_floor=thin, minimum_pt=floor)

    for check_id, message in (
        ("legend_data_overlap", "Python does not measure legend/data occlusion. Inspect the final export; browser evidence is renderer-specific."),
        ("space_and_density", "Python does not run the browser ink/overdraw/empty-space/bar-distribution measurements. Review the final figure; do not infer information from ink coverage."),
        ("article_placement", "Width checks use the selected reference, not a compiled article. Caption/body collisions, footer fit and actual insertion scale remain unverified."),
    ):
        report.add("reference." + check_id, NOT_CHECKED, message)
    return report
