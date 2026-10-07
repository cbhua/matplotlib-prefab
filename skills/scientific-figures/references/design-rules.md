# Design rules and where the numbers come from

Read this when you need to change a style value, explain one, or judge whether a
rendered figure is acceptable.

## The values are provisional

`references/profiles/single-column.json` carries `"status": "provisional"`. Every
number in it is an initial project choice made to get a working pipeline, **not a
journal or conference requirement**. Do not describe them to anyone as a
publication standard, and do not cite them as one. The repository owner is expected
to review and finalise them by hand.

## One source of truth

The profile is the only place style numbers live. Templates
(`assets/templates/*.py`) decide *which artists* to draw; every size, colour, dash
pattern, tick count and export setting is read from the profile at draw time. There
are no fallback defaults hidden in the templates and no `rcParams` edits outside
`figure_core.style_context`.

The practical consequence, which the test suite enforces: edit a number in the
profile, re-render, and both the line and the bar figure use the new value.

To see a change rather than reason about it, run `python tests/render_gallery.py`
and open `tests/output/index.md`. It renders every prefab spec in `tests/data/`
with the current profile and prints the values in force next to the pictures, so
the sizes, palette, marker shapes and dash fallback can be judged by eye. The
committed sheet is checked against the profile, so it can never quietly go stale.

## Sizes are physical

A matplotlib point is 1/72 inch **of the final figure**. Because the canvas is
created at a fixed size in inches and saved without `bbox_inches="tight"`, a 9 pt
axis label is 9 pt on the printed page.

* Width comes from `canvas.width_mm` (85 mm — one column of a typical two-column
  paper).
* Height is *derived*: `width × canvas.aspect_ratio` (0.618). The profile never
  stores a height that could drift out of agreement with the width.
* `output.png_dpi` changes only the raster resolution of the preview. It never
  changes text size, line width or the PDF page size. The test suite checks this
  by rendering the same spec at 100 and 400 DPI and confirming the PDF page is
  identical.

This is also why `bbox_inches="tight"` is avoided: it re-crops the canvas, so the
saved file would no longer be the size the profile promises. If you ever add
cropping, you must prove the final size still matches the profile.

## Type

| Role | Provisional value |
| --- | --- |
| Axis labels | 9 pt |
| Tick labels, legend | 8 pt |
| Title (optional) | 10 pt |

Each of those has an optional per-axis override, so the two axes need not share a
size or a weight:

| Shared field | Overrides that refine it |
| --- | --- |
| `fonts.size_axis_label_pt` | `fonts.size_x_label_pt`, `fonts.size_y_label_pt` |
| `fonts.size_tick_pt` | `fonts.size_xtick_pt`, `fonts.size_ytick_pt` |
| `fonts.weight` | `fonts.weight_x_label`, `fonts.weight_y_label`, `fonts.weight_xtick`, `fonts.weight_ytick`, `fonts.weight_legend`, `fonts.weight_title` |

An override that is absent or `null` falls back to the shared field, so a profile
written before these existed renders exactly what it did before — that is a test,
not an intention. Resolution is `figure_core.font_size(profile, role)` and
`font_weight(profile, role)` for the roles `x_label`, `y_label`, `xtick`, `ytick`,
`legend`, `title`; `resolved_type(profile)` returns all of them at once and is what
goes into the report and the browser tool's hand-off.

Weights are validated against the set matplotlib actually applies. An
unrecognised weight is rejected rather than silently ignored: a style control that
appears to do something and does not is worse than one that refuses.

Tick-label weight cannot be set through rcParams, so it is applied to the label
artists after the template has drawn and re-applied on every draw. The
`font_sizes` check verifies the weight as well as the size on every text artist,
which is what turns "the field is in the profile" into "the drawing took it".

Family is DejaVu Sans at normal weight — chosen because it ships with matplotlib,
so a fresh checkout renders identically without font installation. Ordinary text is
upright; italics are reserved for maths variables, which mathtext handles.
`mathtext.fontset` is `dejavusans` so maths matches the body text.

No LaTeX installation is required. `pdf.fonttype` is 42, so text in the PDF stays
selectable, searchable and editable rather than being converted to outlines.

If a requested font is missing, matplotlib silently substitutes one and missing
characters export as empty boxes. The report refuses to hide that: `font_resolution`
warns on substitution, and `glyph_coverage` fails when a character is absent from
the resolved font.

## Lines, markers and colour

| Role | Provisional value |
| --- | --- |
| Data lines | 1.2 pt |
| Axes spines and tick marks | 0.6 pt |
| Markers | 4 pt |

Colour is the primary way to tell series apart, using the Paul Tol bright
qualitative palette (`#4477AA`, `#EE6677`, `#228833`, `#CCBB44`, `#66CCEE`,
`#AA3377`), chosen for reasonable separation for common colour-vision deficiencies.
Marker shape is bound to the same series slot as colour, so shape reinforces colour
rather than encoding something else — the figure stays readable in greyscale and
for readers who cannot separate the hues.

Dash pattern is the overflow channel. Series 1..6 are solid in distinct colours;
series 7 reuses colour 1 with a dashed line, and so on. Past
`len(colours) × len(dash_patterns)` combinations the render is an error, not a
silent recycle.

Markers are thinned with `markevery` so at most
`lines.max_markers_per_series` (12) appear per series. Every data point is still
plotted — the check `line_data_integrity` verifies the drawn point count equals the
input count — the markers just stop turning a dense curve into a solid band.

A single-series bar chart uses one colour for every bar. Giving each category its
own colour would encode a grouping that is not in the data.

## Axes and layout

* Top and right spines are hidden; the panel is bounded by data, not by a box.
* At most 6 major ticks per axis (`MaxNLocator`), so labels stay readable at 85 mm.
* A faint dotted y grid at alpha 0.3, drawn under the data (`set_axisbelow`).
* `layout.engine` is `constrained`, and it is the *only* layout mechanism used.
  Mixing constrained layout with `tight_layout` or manual `subplots_adjust`
  produces conflicting results, so the profile validator rejects any other value.
* `layout.pad_pt` (1.5 pt) is the margin constrained layout leaves around the
  content.

Bar charts get a fixed x limit of ±0.5 beyond the outermost bar so the first and
last bars are not glued to the spines, and a y range that always contains zero:
padding is added only on the non-zero side, so all-positive bars sit exactly on the
baseline.

## Legends

`legend.show_for_single_series` is `false`: a one-series line chart names its data
in the y label and the caption, so a legend would only take space. Two or more
series always get a legend — the `legend_present` check fails otherwise.

Placement is `"best"`, which minimises overlap with the data but does not
guarantee it. No automatic check can prove a legend is clear of the data, which is
one of the reasons the visual review is a required, human/agent step.

## What the checks can and cannot tell you

Exact and trustworthy:

* canvas size, PDF page size, PNG pixel size;
* exactly one axes panel;
* font size per text role, resolved font family, glyph coverage;
* line point counts and series order; bar count, category order, zero in range.

Heuristic — reported as warnings, never as proof:

* `text_within_canvas` compares text bounding boxes against the canvas. Bounding
  boxes are conservative, so a warning means "look at this", not "this is broken".
* `tick_label_overlap` compares neighbouring tick-label boxes. Deliberately
  overlapping artists elsewhere in a figure are not flagged, and it says nothing
  about whether a legend hides data.
* `panel_area` flags a plotting area squeezed below a quarter of the canvas.

Not attempted at all:

* whether the figure is *right*: units, scaling, statistics, whether a line chart
  was the correct choice;
* whether colours survive printing, projection or a particular kind of colour
  blindness;
* whether the legend covers data.

`visual_review` is therefore always `not_checked`. Nothing in the pipeline fills it
in. Only a person or an agent that actually opens `figure.png` can close it, and if
that is impossible in the environment, the honest report is that the visual review
did not happen.

Rectangular grids use the same physical type and line sizes on a shared canvas.
Their plot-area check is relative to each allocated cell, and they additionally
check overlaps between panel decorations. Wide profiles can span columns.

## Deliberately out of scope in this version

Nonrectangular panel layouts, scatter, histogram, heatmap and 3D charts,
stacked or grouped bars, twin axes, error bars, log axes, venue-specific profiles,
CSV input inference, interactive output. Each of those arrives as a new profile or
a new template, not as options bolted onto these two.

## Background reading

These informed the approach; none is a dependency.

* tueplots — figure sizing for papers: https://github.com/pnkraemer/tueplots
* Matching figure size to a LaTeX document: https://jwalton.info/Embed-Publication-Matplotlib-Latex/
* `savefig` reference: https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.savefig.html
* Paul Tol's qualitative colour schemes: https://sronpersonalpages.nl/~pault/
