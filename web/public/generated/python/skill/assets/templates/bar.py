"""Bar template: one value per named category, drawn as vertical bars.

This is a category-vs-value comparison, not a histogram: the values are used
as-is and nothing is binned or counted. Negative values are allowed; the y
range always contains zero and the zero baseline is always drawn, so bar
lengths stay readable against a common origin.
"""

from __future__ import annotations

from typing import Any, Dict

import figure_core

KIND = "bar"


def _y_limits(values, margin: float):
    low = min(0.0, min(values))
    high = max(0.0, max(values))
    if low == high:  # every value is exactly zero
        return 0.0, 1.0
    pad = (high - low) * margin
    return (low if low == 0.0 else low - pad), (high if high == 0.0 else high + pad)


def draw(ax, spec: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    categories = spec["categories"]
    values = spec["values"]
    bar_cfg = profile["bar"]

    # A single series gets a single colour: giving each category its own colour
    # would encode a grouping that does not exist in the data.
    color = profile["colors"]["categorical"][0]
    positions = list(range(len(categories)))

    ax.bar(
        positions,
        values,
        width=float(bar_cfg["width_fraction"]),
        color=color,
        edgecolor=profile["colors"]["axes"],
        linewidth=float(bar_cfg["edge_linewidth_pt"]),
        zorder=2,
    )

    figure_core.apply_axes_style(ax, profile)

    ax.set_xticks(positions)
    ax.set_xticklabels(
        categories,
        rotation=float(bar_cfg["category_label_rotation_deg"]),
        ha="right" if float(bar_cfg["category_label_rotation_deg"]) else "center",
    )
    ax.set_xlim(-0.5 - float(profile["axes"]["margin_x"]), len(categories) - 0.5 + float(profile["axes"]["margin_x"]))

    low, high = _y_limits(values, float(profile["axes"]["margin_y"]))
    ax.set_ylim(low, high)

    ax.axhline(
        0.0,
        color=profile["colors"]["axes"],
        linewidth=float(bar_cfg["zero_line_linewidth_pt"]),
        zorder=3,
    )

    figure_core.apply_labels(ax, spec, profile)

    return {
        "kind": KIND,
        "n_categories": len(categories),
        "categories": list(categories),
        "n_series": 1,
        "legend_drawn": False,
        "has_negative": any(v < 0 for v in values),
        "zero_baseline": True,
        "color": color,
    }
