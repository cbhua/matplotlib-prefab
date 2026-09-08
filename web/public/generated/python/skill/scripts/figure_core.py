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
import io
import json
import math
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

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

# Optional per-axis overrides. Every one of these has a fallback to the shared
# field it refines, so a profile written before they existed renders exactly what
# it always did. They exist because "the axis label size" is one number only
# until someone needs a long y label two points smaller than the x label.
#
# The value is the shared field it falls back to.
_OPTIONAL_SIZE_OVERRIDES = {
    ("fonts", "size_x_label_pt"): ("fonts", "size_axis_label_pt"),
    ("fonts", "size_y_label_pt"): ("fonts", "size_axis_label_pt"),
    ("fonts", "size_xtick_pt"): ("fonts", "size_tick_pt"),
    ("fonts", "size_ytick_pt"): ("fonts", "size_tick_pt"),
}

_OPTIONAL_WEIGHT_OVERRIDES = {
    ("fonts", "weight_x_label"): ("fonts", "weight"),
    ("fonts", "weight_y_label"): ("fonts", "weight"),
    ("fonts", "weight_xtick"): ("fonts", "weight"),
    ("fonts", "weight_ytick"): ("fonts", "weight"),
    ("fonts", "weight_legend"): ("fonts", "weight"),
    ("fonts", "weight_title"): ("fonts", "weight"),
}

# matplotlib's own set. Numeric weights (100-900) are allowed too; anything else
# silently falls back to normal inside matplotlib, which is exactly the kind of
# knob-that-does-nothing this project refuses to ship.
_FONT_WEIGHT_NAMES = (
    "ultralight", "light", "normal", "regular", "book", "medium", "roman",
    "semibold", "demibold", "demi", "bold", "heavy", "extra bold", "black",
)

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

    for (section, key), (fallback_section, fallback_key) in _OPTIONAL_SIZE_OVERRIDES.items():
        block = profile.get(section) or {}
        if key not in block or block[key] is None:
            continue
        value = block[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ProfileError(
                "profile.%s.%s is an optional override of profile.%s.%s and must be a "
                "number, got %s." % (section, key, fallback_section, fallback_key,
                                     type(value).__name__)
            )
        if not math.isfinite(float(value)) or float(value) <= 0:
            raise ProfileError(
                "profile.%s.%s must be a finite, strictly positive point size, got %r."
                % (section, key, value)
            )

    for (section, key), (fallback_section, fallback_key) in _OPTIONAL_WEIGHT_OVERRIDES.items():
        block = profile.get(section) or {}
        if key not in block or block[key] is None:
            continue
        _validate_weight(block[key], "profile.%s.%s" % (section, key))

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
    if "weight" in fonts:
        _validate_weight(fonts["weight"], "profile.fonts.weight")
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


def _validate_weight(value: Any, where: str) -> None:
    """A weight matplotlib will actually apply, not one it quietly ignores."""
    if isinstance(value, bool):
        raise ProfileError("%s must be a weight name or a number, got a boolean." % where)
    if isinstance(value, (int, float)):
        if not (100 <= float(value) <= 1000):
            raise ProfileError(
                "%s is %r; a numeric font weight must be between 100 and 1000." % (where, value)
            )
        return
    if not isinstance(value, str) or value.strip().lower() not in _FONT_WEIGHT_NAMES:
        raise ProfileError(
            "%s is %r, which matplotlib does not recognise as a font weight. Use a number "
            "between 100 and 1000, or one of: %s. An unrecognised weight would be silently "
            "dropped, leaving a control that appears to do nothing."
            % (where, value, ", ".join(_FONT_WEIGHT_NAMES))
        )


# --------------------------------------------------------------------------
# Resolving a style role to a number
# --------------------------------------------------------------------------
#
# One function answers "how big is the x tick label", and everything — the
# renderer, the checks, the browser panel, the exported hand-off — asks it. A UI
# control that wrote to a field the renderer never read would be the worst kind
# of bug here: visibly wrong output with a plausible-looking configuration.

SIZE_ROLES = {
    "x_label": (("fonts", "size_x_label_pt"), ("fonts", "size_axis_label_pt")),
    "y_label": (("fonts", "size_y_label_pt"), ("fonts", "size_axis_label_pt")),
    "xtick": (("fonts", "size_xtick_pt"), ("fonts", "size_tick_pt")),
    "ytick": (("fonts", "size_ytick_pt"), ("fonts", "size_tick_pt")),
    "legend": (None, ("fonts", "size_legend_pt")),
    "title": (None, ("fonts", "size_title_pt")),
}

WEIGHT_ROLES = {
    "x_label": ("weight_x_label", "weight"),
    "y_label": ("weight_y_label", "weight"),
    "xtick": ("weight_xtick", "weight"),
    "ytick": ("weight_ytick", "weight"),
    "legend": ("weight_legend", "weight"),
    "title": ("weight_title", "weight"),
}


def font_size(profile: Dict[str, Any], role: str) -> float:
    """The point size for one text role, override first, shared field second."""
    try:
        override, fallback = SIZE_ROLES[role]
    except KeyError:
        raise ProfileError(
            "Unknown text role %r. Known roles: %s." % (role, ", ".join(sorted(SIZE_ROLES)))
        ) from None
    if override is not None:
        value = profile.get(override[0], {}).get(override[1])
        if value is not None:
            return float(value)
    return float(profile[fallback[0]][fallback[1]])


def font_weight(profile: Dict[str, Any], role: str) -> Any:
    """The weight for one text role, override first, then the profile's default."""
    override, fallback = WEIGHT_ROLES[role]
    fonts = profile.get("fonts", {})
    value = fonts.get(override)
    if value is None:
        value = fonts.get(fallback, "normal")
    return value


def resolved_type(profile: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Every text role's size and weight after the fallbacks have been applied.

    This is what goes into the exported hand-off and the reports: the numbers
    that were actually used, not the fields that happened to be written down.
    """
    return {
        role: {"size_pt": font_size(profile, role), "weight": font_weight(profile, role)}
        for role in SIZE_ROLES
    }


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
        # axes.labelsize is a single rcParam and the two axis labels can now
        # differ, so it carries the shared value and apply_labels sets each axis
        # explicitly. The tick sizes *are* separate rcParams, so they are set
        # from the resolved per-axis values here.
        "axes.labelsize": float(fonts["size_axis_label_pt"]),
        "axes.titlesize": font_size(profile, "title"),
        "axes.titleweight": font_weight(profile, "title"),
        "axes.labelweight": fonts.get("weight", "normal"),
        "xtick.labelsize": font_size(profile, "xtick"),
        "ytick.labelsize": font_size(profile, "ytick"),
        "legend.fontsize": font_size(profile, "legend"),
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
    """Set the axis labels and the title at their own resolved size and weight."""
    ax.set_xlabel(
        spec["x_label"],
        fontsize=font_size(profile, "x_label"),
        fontweight=font_weight(profile, "x_label"),
    )
    ax.set_ylabel(
        spec["y_label"],
        fontsize=font_size(profile, "y_label"),
        fontweight=font_weight(profile, "y_label"),
    )
    title = spec.get("title")
    if title:
        ax.set_title(
            title,
            fontsize=font_size(profile, "title"),
            fontweight=font_weight(profile, "title"),
        )


def apply_tick_type(ax, profile: Dict[str, Any]) -> None:
    """Give each axis's tick labels their own size and weight.

    matplotlib has rcParams for tick label *size* per axis but none for weight,
    so the weight is set on the label artists. This runs after the template has
    drawn — the locators and the limits are settled by then, so these are the
    labels that will be printed — and it re-applies on every draw, because a
    constrained layout pass can rebuild the tick artists underneath us and a
    weight applied only once would quietly disappear.
    """
    settings = (
        (ax.xaxis, font_size(profile, "xtick"), font_weight(profile, "xtick")),
        (ax.yaxis, font_size(profile, "ytick"), font_weight(profile, "ytick")),
    )

    def apply(_event=None):
        for axis, size, weight in settings:
            for label in axis.get_ticklabels():
                label.set_fontsize(size)
                label.set_fontweight(weight)

    apply()
    ax.figure.canvas.mpl_connect("draw_event", apply)


def apply_legend_type(ax, profile: Dict[str, Any]) -> None:
    """The legend's own weight; its size is already an rcParam."""
    legend = ax.get_legend()
    if legend is None:
        return
    weight = font_weight(profile, "legend")
    size = font_size(profile, "legend")
    for text in legend.get_texts():
        text.set_fontsize(size)
        text.set_fontweight(weight)


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


# --------------------------------------------------------------------------
# Templates and the shared in-memory drawing path
# --------------------------------------------------------------------------
#
# Everything that draws a figure goes through here: render.py's CLI, the
# conference-context evaluator and the browser worker in web/. There is exactly
# one implementation of "which template, drawn how, at what size", so a figure
# previewed in the browser and a figure rendered from the command line cannot
# drift apart by having two code paths.

def skill_root_dir() -> str:
    """The skill directory this module lives in (``.../scientific-figures``)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def template_path(kind: str, skill_root: Optional[str] = None) -> str:
    root = skill_root or skill_root_dir()
    return os.path.join(root, "assets", "templates", "%s.py" % kind)


def load_template(kind: str, skill_root: Optional[str] = None):
    """Load the template module for ``kind`` from the skill's assets directory."""
    import importlib.util
    import sys

    path = template_path(kind, skill_root)
    if not os.path.isfile(path):
        raise SpecError("No template found for kind %r (looked for %s)." % (kind, path))
    module_name = "scientific_figures_template_%s" % kind
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def drawn_figure(
    spec: Dict[str, Any],
    profile: Dict[str, Any],
    skill_root: Optional[str] = None,
):
    """Draw one validated spec with one validated profile and yield the live figure.

    The profile's rc context stays open for the whole ``with`` block, so anything
    the caller does with the figure — exporting it, measuring it, checking it —
    sees the same style the artists were drawn under. The figure is always
    closed, including on the way out of an exception, which is what keeps a
    long-lived process (a worker answering slider moves, a test session) from
    accumulating figures.
    """
    import matplotlib.pyplot as plt

    template = load_template(spec["kind"], skill_root)
    with style_context(profile):
        fig, ax = create_figure(profile)
        try:
            drawn = template.draw(ax, spec, profile)
            # The per-axis type overrides are applied here rather than in the
            # templates: a template decides which artists exist, not how big
            # their text is, and putting this in one place means line and bar
            # cannot drift apart on it.
            apply_tick_type(ax, profile)
            apply_legend_type(ax, profile)
            yield fig, ax, drawn
        finally:
            plt.close(fig)


# A fixed salt makes matplotlib's SVG element ids a deterministic function of the
# content instead of a fresh uuid per run, so two renders of the same figure can
# be compared as text. It changes nothing about the drawing itself.
SVG_HASHSALT = "matplotlib-prefab"

SVG_RC = {
    # Text becomes outlines, so the SVG carries its own glyph shapes and does not
    # depend on the viewer having the font. The paper page's HTML type is a
    # separate matter and is calibrated on its own.
    "svg.fonttype": "path",
    "svg.hashsalt": SVG_HASHSALT,
}


def figure_to_svg(fig, profile: Dict[str, Any]) -> str:
    """Serialise a figure to an SVG string, with nothing run-dependent in it.

    ``Date`` metadata is suppressed and the element-id salt is fixed, so the same
    spec and profile give byte-identical output on the same matplotlib. That is
    what makes browser-vs-local comparison a real check rather than a diff of
    timestamps.
    """
    buffer = io.StringIO()
    with matplotlib.rc_context(rc=SVG_RC):
        fig.savefig(buffer, format="svg", metadata={"Date": None})
    return buffer.getvalue()


def render_to_svg(
    spec: Dict[str, Any],
    profile: Dict[str, Any],
    skill_root: Optional[str] = None,
    checks: bool = False,
) -> Dict[str, Any]:
    """Validate, draw and return an SVG plus what was drawn. Touches no files.

    This is the entry point the browser worker calls. It takes and returns plain
    Python objects so that the same call works over a Pyodide bridge, and it
    reports the physical size separately from the SVG because the page needs the
    millimetres to place the figure, not the pixels.

    With ``checks=True`` it also runs the live half of the ordinary check suite —
    the same functions ``render.py`` runs, not a lighter version — so a preview
    can say that the tick labels have started colliding instead of showing a
    crowded figure in silence.
    """
    valid_spec = validate_spec(spec)
    valid_profile = validate_profile(profile)
    width_in, height_in = figure_size_inches(valid_profile)
    report = None
    with drawn_figure(valid_spec, valid_profile, skill_root) as (fig, ax, drawn):
        svg = figure_to_svg(fig, valid_profile)
        if checks:
            import inspect_figure

            report = inspect_figure.inspect_live(fig, ax, valid_spec, valid_profile, drawn)
    return {
        "svg": svg,
        "report": report,
        "drawn": drawn,
        "spec": valid_spec,
        "profile": valid_profile,
        "width_in": width_in,
        "height_in": height_in,
        "width_mm": width_in * MM_PER_INCH,
        "height_mm": height_in * MM_PER_INCH,
    }


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
