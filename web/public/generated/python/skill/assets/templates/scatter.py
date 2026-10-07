"""Scatter template: draw every sample as a marker without connecting lines.

The template owns *what* is drawn (which artists, in which order) and nothing
else. Sizes, colours, dash patterns, tick counts and output behaviour all come
from the profile via ``figure_core``; there are no style defaults here.
"""

from __future__ import annotations

from typing import Any, Dict

import figure_core

KIND = "scatter"


def draw(ax, spec: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    from matplotlib.ticker import MaxNLocator

    x = spec["x"]
    series = spec["series"]
    styles = figure_core.series_styles(len(series), profile)

    lines_cfg = profile["lines"]

    drawn = []
    for item, style in zip(series, styles):
        style = {**style, "linestyle": "None"}
        ax.plot(
            x,
            item["y"],
            label=item["name"],
            color=style["color"],
            linestyle="None",
            linewidth=float(lines_cfg["data_linewidth_pt"]),
            marker=style["marker"],
            markersize=float(lines_cfg["marker_size_pt"]),
            markevery=1,
            markeredgewidth=0.0,
            solid_capstyle="round",
        )
        drawn.append({"name": item["name"], "n_points": len(item["y"]), "style": style})

    figure_core.apply_axes_style(ax, profile)
    ax.xaxis.set_major_locator(
        MaxNLocator(nbins=int(profile["axes"]["max_xticks"]) - 1, min_n_ticks=2)
    )
    ax.margins(x=float(profile["axes"]["margin_x"]), y=float(profile["axes"]["margin_y"]))

    figure_core.apply_labels(ax, spec, profile)
    legend_drawn = figure_core.apply_legend(ax, profile, len(series))

    return {
        "kind": KIND,
        "series": drawn,
        "n_series": len(series),
        "n_points": len(x),
        "legend_drawn": legend_drawn,
        "marker_every": 1,
    }
