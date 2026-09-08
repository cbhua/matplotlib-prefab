"""Line template: draw a validated line spec onto one axes.

The template owns *what* is drawn (which artists, in which order) and nothing
else. Sizes, colours, dash patterns, tick counts and output behaviour all come
from the profile via ``figure_core``; there are no style defaults here.
"""

from __future__ import annotations

from typing import Any, Dict

import figure_core

KIND = "line"


def draw(ax, spec: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    from matplotlib.ticker import MaxNLocator

    x = spec["x"]
    series = spec["series"]
    styles = figure_core.series_styles(len(series), profile)

    lines_cfg = profile["lines"]
    markers_on = bool(lines_cfg.get("markers_enabled", True))
    every = figure_core.marker_every(len(x), profile)

    drawn = []
    for item, style in zip(series, styles):
        ax.plot(
            x,
            item["y"],
            label=item["name"],
            color=style["color"],
            linestyle=style["linestyle"],
            linewidth=float(lines_cfg["data_linewidth_pt"]),
            marker=style["marker"] if markers_on else "None",
            markersize=float(lines_cfg["marker_size_pt"]),
            markevery=every,
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
        "marker_every": every if markers_on else None,
    }
