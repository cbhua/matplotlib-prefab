"""Shared validation, style resolution and export logic for the scientific-figures skill.

This module is self-contained: it only depends on the Python standard library,
numpy and matplotlib, and it never imports anything from the repository root.
Copying ``skills/scientific-figures/`` somewhere else keeps it working.

Responsibilities
----------------
* parse and validate the JSON figure spec (the data contract),
* parse and validate the style profile (the single source of style truth),
* turn a profile into matplotlib rcParams / artist styles,
* create the single-panel figure and export it at a fixed physical size.

Templates draw artists; they do not decide style numbers or output behaviour.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
from typing import Any, Dict, Iterable, List, Tuple

import matplotlib

SPEC_SCHEMA_VERSION = "1"
MM_PER_INCH = 25.4
PT_PER_INCH = 72.0

SUPPORTED_KINDS = ("line", "bar")


class SpecError(ValueError):
    """Raised when the figure spec violates the data contract."""


class ProfileError(ValueError):
    """Raised when the style profile is missing keys or holds invalid values."""


# --------------------------------------------------------------------------
# JSON loading
# --------------------------------------------------------------------------

def _reject_json_constant(name: str):
    raise SpecError(
        "JSON contains the non-finite literal %r. Numeric data must be finite; "
        "fix the data or drop the affected points before rendering." % name
    )


def load_json(path: str, what: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        raise SpecError("%s file not found: %s" % (what, path))
    with open(path, "r", encoding="utf-8") as handle:
        try:
            data = json.load(handle, parse_constant=_reject_json_constant)
        except json.JSONDecodeError as exc:
            raise SpecError("%s file %s is not valid JSON: %s" % (what, path, exc)) from None
    if not isinstance(data, dict):
        raise SpecError("%s file %s must contain a JSON object at the top level." % (what, path))
    return data


# --------------------------------------------------------------------------
# Spec validation
# --------------------------------------------------------------------------

_COMMON_KEYS = {"schema_version", "kind", "x_label", "y_label", "title"}
_KIND_KEYS = {
    "line": {"x", "series"},
    "bar": {"categories", "values"},
}


def _check_unknown_keys(obj: Dict[str, Any], allowed: Iterable[str], where: str) -> None:
    unknown = sorted(set(obj) - set(allowed))
    if unknown:
        raise SpecError(
            "%s contains unknown field(s) %s. Allowed fields: %s. "
            "Unknown fields are rejected so that a typo cannot be silently ignored."
            % (where, ", ".join(repr(k) for k in unknown), ", ".join(sorted(allowed)))
        )


def _require(obj: Dict[str, Any], key: str, where: str) -> Any:
    if key not in obj:
        raise SpecError("%s is missing the required field %r." % (where, key))
    return obj[key]


def _as_str(value: Any, where: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise SpecError("%s must be a string, got %s." % (where, type(value).__name__))
    if not allow_empty and not value.strip():
        raise SpecError("%s must not be empty." % where)
    return value


def _as_number(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpecError(
            "%s must be a number, got %s (%r)." % (where, type(value).__name__, value)
        )
    number = float(value)
    if not math.isfinite(number):
        raise SpecError("%s must be finite, got %r." % (where, value))
    return number


def _as_number_list(value: Any, where: str) -> List[float]:
    if not isinstance(value, list):
        raise SpecError("%s must be a JSON array of numbers, got %s." % (where, type(value).__name__))
    if not value:
        raise SpecError("%s must not be empty." % where)
    return [_as_number(item, "%s[%d]" % (where, i)) for i, item in enumerate(value)]


def validate_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a figure spec and return a normalised copy.

    The returned dict is what gets snapshotted as ``spec.json`` in the output
    directory, so it is exactly what was drawn. Data order is preserved: nothing
    is sorted, smoothed, deduplicated or aggregated.
    """
    if not isinstance(spec, dict):
        raise SpecError("The figure spec must be a JSON object.")

    version = _as_str(_require(spec, "schema_version", "spec"), "spec.schema_version")
    if version != SPEC_SCHEMA_VERSION:
        raise SpecError(
            "spec.schema_version is %r but this skill implements version %r."
            % (version, SPEC_SCHEMA_VERSION)
        )

    kind = _as_str(_require(spec, "kind", "spec"), "spec.kind")
    if kind not in SUPPORTED_KINDS:
        raise SpecError(
            "spec.kind is %r, which this skill does not support. Supported kinds: %s. "
            "Multi-panel, two-column, scatter, histogram, heatmap and 3D figures are "
            "explicitly out of scope for this version."
            % (kind, ", ".join(SUPPORTED_KINDS))
        )

    _check_unknown_keys(spec, _COMMON_KEYS | _KIND_KEYS[kind], "spec")

    normalised: Dict[str, Any] = {
        "schema_version": version,
        "kind": kind,
        "x_label": _as_str(_require(spec, "x_label", "spec"), "spec.x_label", allow_empty=True),
        "y_label": _as_str(_require(spec, "y_label", "spec"), "spec.y_label", allow_empty=True),
    }

    title = spec.get("title", None)
    if title is not None:
        title = _as_str(title, "spec.title", allow_empty=True)
    normalised["title"] = title

    if kind == "line":
        normalised.update(_validate_line(spec))
    else:
        normalised.update(_validate_bar(spec))
    return normalised


def _validate_line(spec: Dict[str, Any]) -> Dict[str, Any]:
    x = _as_number_list(_require(spec, "x", "spec"), "spec.x")

    raw_series = _require(spec, "series", "spec")
    if not isinstance(raw_series, list) or not raw_series:
        raise SpecError("spec.series must be a non-empty JSON array of series objects.")

    series: List[Dict[str, Any]] = []
    seen: Dict[str, int] = {}
    for index, item in enumerate(raw_series):
        where = "spec.series[%d]" % index
        if not isinstance(item, dict):
            raise SpecError("%s must be an object with 'name' and 'y'." % where)
        _check_unknown_keys(item, {"name", "y"}, where)
        name = _as_str(_require(item, "name", where), "%s.name" % where)
        if name in seen:
            raise SpecError(
                "%s.name is %r, which duplicates spec.series[%d].name. "
                "Series names must be unique so the legend stays unambiguous."
                % (where, name, seen[name])
            )
        seen[name] = index
        y = _as_number_list(_require(item, "y", where), "%s.y" % where)
        if len(y) != len(x):
            raise SpecError(
                "%s.y has %d values but spec.x has %d. Every series must have the "
                "same length as x." % (where, len(y), len(x))
            )
        series.append({"name": name, "y": y})

    return {"x": x, "series": series}


def _validate_bar(spec: Dict[str, Any]) -> Dict[str, Any]:
    raw_categories = _require(spec, "categories", "spec")
    if not isinstance(raw_categories, list) or not raw_categories:
        raise SpecError("spec.categories must be a non-empty JSON array of strings.")

    categories: List[str] = []
    seen: Dict[str, int] = {}
    for index, item in enumerate(raw_categories):
        name = _as_str(item, "spec.categories[%d]" % index)
        if name in seen:
            raise SpecError(
                "spec.categories[%d] is %r, which duplicates spec.categories[%d]. "
                "Bar categories must be unique." % (index, name, seen[name])
            )
        seen[name] = index
        categories.append(name)

    values = _as_number_list(_require(spec, "values", "spec"), "spec.values")
    if len(values) != len(categories):
        raise SpecError(
            "spec.values has %d entries but spec.categories has %d. A bar chart "
            "compares one value per named category; it is not a histogram and does "
            "not bin raw samples." % (len(values), len(categories))
        )
    return {"categories": categories, "values": values}


def load_spec(path: str) -> Dict[str, Any]:
    return validate_spec(load_json(path, "Spec"))


# --------------------------------------------------------------------------
# Profile validation
# --------------------------------------------------------------------------

_PROFILE_NUMBERS = {
    "canvas": ["width_mm", "aspect_ratio"],
    "fonts": [
        "size_axis_label_pt",
        "size_tick_pt",
        "size_legend_pt",
        "size_title_pt",
    ],
    "lines": [
        "data_linewidth_pt",
        "axes_linewidth_pt",
        "tick_linewidth_pt",
        "tick_length_pt",
        "tick_pad_pt",
        "marker_size_pt",
        "max_markers_per_series",
    ],
    "axes": [
        "max_xticks",
        "max_yticks",
        "margin_x",
        "margin_y",
        "grid_alpha",
        "grid_linewidth_pt",
    ],
    "bar": [
        "width_fraction",
        "edge_linewidth_pt",
        "zero_line_linewidth_pt",
        "category_label_rotation_deg",
    ],
    "legend": ["columns", "handlelength", "border_pad", "label_spacing"],
    "layout": ["pad_pt"],
    "output": ["png_dpi"],
}

_STRICTLY_POSITIVE = {
    ("canvas", "width_mm"),
    ("canvas", "aspect_ratio"),
    ("fonts", "size_axis_label_pt"),
    ("fonts", "size_tick_pt"),
    ("fonts", "size_legend_pt"),
    ("fonts", "size_title_pt"),
    ("lines", "data_linewidth_pt"),
    ("lines", "axes_linewidth_pt"),
    ("lines", "marker_size_pt"),
    ("lines", "max_markers_per_series"),
    ("axes", "max_xticks"),
    ("axes", "max_yticks"),
    ("bar", "width_fraction"),
    ("legend", "columns"),
    ("output", "png_dpi"),
}


def validate_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a style profile and return it unchanged (as the resolved profile)."""
    if not isinstance(profile, dict):
        raise ProfileError("The profile must be a JSON object.")

    for section, keys in _PROFILE_NUMBERS.items():
        block = profile.get(section)
        if not isinstance(block, dict):
            raise ProfileError("profile.%s is missing or is not an object." % section)
        for key in keys:
            if key not in block:
                raise ProfileError("profile.%s.%s is missing." % (section, key))
            value = block[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ProfileError(
                    "profile.%s.%s must be a number, got %s."
                    % (section, key, type(value).__name__)
                )
            number = float(value)
            if not math.isfinite(number):
                raise ProfileError("profile.%s.%s must be finite." % (section, key))
            if (section, key) in _STRICTLY_POSITIVE and number <= 0:
                raise ProfileError(
                    "profile.%s.%s must be strictly positive, got %r."
                    % (section, key, value)
                )
            if number < 0:
                raise ProfileError(
                    "profile.%s.%s must not be negative, got %r." % (section, key, value)
                )

    colors = profile.get("colors")
    if not isinstance(colors, dict):
        raise ProfileError("profile.colors is missing or is not an object.")
    palette = colors.get("categorical")
    if not isinstance(palette, list) or not palette:
        raise ProfileError("profile.colors.categorical must be a non-empty array of colours.")
    for key in ("text", "axes", "grid"):
        if not isinstance(colors.get(key), str):
            raise ProfileError("profile.colors.%s must be a colour string." % key)

    fonts = profile["fonts"]
    if not isinstance(fonts.get("family"), str) or not fonts["family"].strip():
        raise ProfileError("profile.fonts.family must be a non-empty font family name.")
    if not isinstance(fonts.get("fallbacks", []), list):
        raise ProfileError("profile.fonts.fallbacks must be an array of font family names.")

    lines = profile["lines"]
    for key in ("markers", "dash_patterns"):
        if not isinstance(lines.get(key), list) or not lines[key]:
            raise ProfileError("profile.lines.%s must be a non-empty array." % key)

    if profile.get("layout", {}).get("engine") not in ("constrained",):
        raise ProfileError(
            "profile.layout.engine must be 'constrained'. This version deliberately "
            "uses one layout mechanism only; mixing it with tight_layout or manual "
            "subplot adjustment produces conflicting results."
        )

    if not isinstance(profile.get("canvas", {}).get("background"), str):
        raise ProfileError("profile.canvas.background must be a colour string.")

    return profile


def load_profile(path: str) -> Dict[str, Any]:
    try:
        raw = load_json(path, "Profile")
    except SpecError as exc:
        raise ProfileError(str(exc)) from None
    return validate_profile(raw)


def default_profile_path(skill_root: str) -> str:
    return os.path.join(skill_root, "references", "profiles", "single-column.json")


# --------------------------------------------------------------------------
# Style resolution
# --------------------------------------------------------------------------

def figure_size_inches(profile: Dict[str, Any]) -> Tuple[float, float]:
    """Return (width, height) in inches.

    Height is always derived from width and aspect ratio, so the profile never
    stores two values that can disagree.
    """
    width_in = float(profile["canvas"]["width_mm"]) / MM_PER_INCH
    height_in = width_in * float(profile["canvas"]["aspect_ratio"])
    return width_in, height_in


def font_family_list(profile: Dict[str, Any]) -> List[str]:
    fonts = profile["fonts"]
    return [fonts["family"]] + list(fonts.get("fallbacks", []))


def rc_params(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Translate the profile into matplotlib rcParams.

    Point sizes are physical: matplotlib points are 1/72 inch of the final
    figure, so DPI only changes raster resolution, never text or line size.
    """
    fonts = profile["fonts"]
    lines = profile["lines"]
    axes = profile["axes"]
    colors = profile["colors"]
    legend = profile["legend"]
    background = profile["canvas"]["background"]

    return {
        "font.family": font_family_list(profile),
        "font.weight": fonts.get("weight", "normal"),
        "font.size": float(fonts["size_tick_pt"]),
        "mathtext.fontset": fonts.get("mathtext_fontset", "dejavusans"),
        "axes.labelsize": float(fonts["size_axis_label_pt"]),
        "axes.titlesize": float(fonts["size_title_pt"]),
        "xtick.labelsize": float(fonts["size_tick_pt"]),
        "ytick.labelsize": float(fonts["size_tick_pt"]),
        "legend.fontsize": float(fonts["size_legend_pt"]),
        "axes.labelcolor": colors["text"],
        "text.color": colors["text"],
        "axes.edgecolor": colors["axes"],
        "xtick.color": colors["axes"],
        "ytick.color": colors["axes"],
        "xtick.labelcolor": colors["text"],
        "ytick.labelcolor": colors["text"],
        "axes.linewidth": float(lines["axes_linewidth_pt"]),
        "xtick.major.width": float(lines["tick_linewidth_pt"]),
        "ytick.major.width": float(lines["tick_linewidth_pt"]),
        "xtick.major.size": float(lines["tick_length_pt"]),
        "ytick.major.size": float(lines["tick_length_pt"]),
        "xtick.major.pad": float(lines["tick_pad_pt"]),
        "ytick.major.pad": float(lines["tick_pad_pt"]),
        "xtick.direction": "out",
        "ytick.direction": "out",
        "lines.linewidth": float(lines["data_linewidth_pt"]),
        "lines.markersize": float(lines["marker_size_pt"]),
        "grid.color": colors["grid"],
        "grid.alpha": float(axes["grid_alpha"]),
        "grid.linewidth": float(axes["grid_linewidth_pt"]),
        "grid.linestyle": axes.get("grid_linestyle", ":"),
        "legend.frameon": bool(legend.get("frame", False)),
        "legend.handlelength": float(legend["handlelength"]),
        "legend.borderpad": float(legend["border_pad"]),
        "legend.labelspacing": float(legend["label_spacing"]),
        "figure.facecolor": background,
        "axes.facecolor": background,
        "savefig.facecolor": background,
        "savefig.transparent": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "axes.unicode_minus": True,
    }


@contextlib.contextmanager
def style_context(profile: Dict[str, Any]):
    """Apply the profile as a *local* rc context.

    Using a context manager rather than mutating rcParams globally means one
    render never leaks style into the next figure drawn in the same process.
    """
    with matplotlib.rc_context(rc=rc_params(profile)):
        yield


def series_styles(count: int, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return one distinguishable style per series.

    Colour is the primary channel; when there are more series than colours the
    dash pattern changes so that reused colours stay separable. Beyond
    ``len(colours) * len(dash_patterns)`` combinations there is no honest way to
    keep series apart, so that is a hard error rather than a silent cycle.
    """
    colors = list(profile["colors"]["categorical"])
    dashes = list(profile["lines"]["dash_patterns"])
    markers = list(profile["lines"]["markers"])
    capacity = len(colors) * len(dashes)
    if count > capacity:
        raise SpecError(
            "The spec has %d series but this profile can only produce %d visually "
            "distinguishable styles (%d colours x %d dash patterns). Reduce the number "
            "of series, split the figure, or extend profile.colors.categorical / "
            "profile.lines.dash_patterns."
            % (count, capacity, len(colors), len(dashes))
        )
    styles = []
    for index in range(count):
        tier = index // len(colors)
        styles.append(
            {
                "color": colors[index % len(colors)],
                "linestyle": dashes[tier % len(dashes)],
                "marker": markers[index % len(markers)],
            }
        )
    return styles


def marker_every(n_points: int, profile: Dict[str, Any]) -> int:
    """Thin markers on dense series so they mark the line instead of hiding it."""
    limit = int(profile["lines"]["max_markers_per_series"])
    if n_points <= limit:
        return 1
    return max(1, int(math.ceil(n_points / float(limit))))


# --------------------------------------------------------------------------
# Figure creation, styling and export
# --------------------------------------------------------------------------

def create_figure(profile: Dict[str, Any]):
    """Create the one and only panel, at the exact physical size of the profile."""
    import matplotlib.pyplot as plt

    width_in, height_in = figure_size_inches(profile)
    fig, ax = plt.subplots(figsize=(width_in, height_in), layout=profile["layout"]["engine"])
    pad_in = float(profile["layout"]["pad_pt"]) / PT_PER_INCH
    engine = fig.get_layout_engine()
    if engine is not None:
        engine.set(w_pad=pad_in, h_pad=pad_in, wspace=0.0, hspace=0.0)
    return fig, ax


def apply_axes_style(ax, profile: Dict[str, Any]) -> None:
    """Apply the profile parts that are not expressible as rcParams."""
    from matplotlib.ticker import MaxNLocator

    axes_cfg = profile["axes"]
    ax.spines["top"].set_visible(bool(axes_cfg.get("spine_top", False)))
    ax.spines["right"].set_visible(bool(axes_cfg.get("spine_right", False)))

    if axes_cfg.get("grid_enabled", False):
        ax.grid(True, axis=axes_cfg.get("grid_axis", "y"))
        ax.set_axisbelow(True)
    else:
        ax.grid(False)

    ax.yaxis.set_major_locator(MaxNLocator(nbins=int(axes_cfg["max_yticks"]) - 1, min_n_ticks=2))


def apply_labels(ax, spec: Dict[str, Any], profile: Dict[str, Any]) -> None:
    fonts = profile["fonts"]
    ax.set_xlabel(spec["x_label"], fontsize=float(fonts["size_axis_label_pt"]))
    ax.set_ylabel(spec["y_label"], fontsize=float(fonts["size_axis_label_pt"]))
    title = spec.get("title")
    if title:
        ax.set_title(title, fontsize=float(fonts["size_title_pt"]))


def apply_legend(ax, profile: Dict[str, Any], n_series: int) -> bool:
    """Add a legend when it carries information. Returns whether one was drawn."""
    legend_cfg = profile["legend"]
    if n_series <= 1 and not legend_cfg.get("show_for_single_series", False):
        return False
    ax.legend(
        loc=legend_cfg.get("location", "best"),
        ncol=int(legend_cfg["columns"]),
        fontsize=float(profile["fonts"]["size_legend_pt"]),
        frameon=bool(legend_cfg.get("frame", False)),
    )
    return True


MANAGED_OUTPUTS = ("figure.pdf", "figure.png", "spec.json", "profile.resolved.json", "report.json")


def export_figure(fig, output_dir: str, profile: Dict[str, Any]) -> Dict[str, str]:
    """Write the deliverables at a fixed physical size.

    ``bbox_inches='tight'`` is deliberately not used: it re-crops the canvas and
    the saved file would no longer match ``profile.canvas``.
    """
    os.makedirs(output_dir, exist_ok=True)
    written: Dict[str, str] = {}
    output_cfg = profile["output"]

    if output_cfg.get("write_pdf", True):
        pdf_path = os.path.join(output_dir, "figure.pdf")
        fig.savefig(pdf_path, format="pdf")
        written["pdf"] = pdf_path
    if output_cfg.get("write_png", True):
        png_path = os.path.join(output_dir, "figure.png")
        fig.savefig(png_path, format="png", dpi=float(output_cfg["png_dpi"]))
        written["png"] = png_path
    return written


def write_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
