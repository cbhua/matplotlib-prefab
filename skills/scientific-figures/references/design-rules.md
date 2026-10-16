# Bundled rendering defaults and mechanics

Read this when changing the bundled renderer or its generic fallback profile.
The skill's descriptive constraints are in [experience-rules.md](experience-rules.md);
conference reference values are separate in
[conference-presets/iclr2026-first.json](conference-presets/iclr2026-first.json).
The defaults below describe the implementation, not additional universal rules.

## The values are provisional

`references/profiles/single-column.json` carries `"status": "provisional"`. Every
number in it is an initial project choice made to get a working pipeline, **not a
journal or conference requirement**. Do not describe them to anyone as a
publication standard, and do not cite them as one. The repository owner is expected
to review and finalise them by hand.

## One source of truth

The resolved profile is the only source of drawing settings. `--preset` merges
the conference's `profile_overrides` over the generic profile; an explicit
`--profile` supplies a full replacement. Templates
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

Browser paper-relative checks and researched stroke references live in
[experience-rules.md](experience-rules.md). They are separate from the provisional
style defaults below and travel with agent handoffs as versioned experience rules.

| Role | Provisional value |
| --- | --- |
| Axis labels | 9 pt |
| Tick labels, legend | 8 pt |
| Title (optional) | 10 pt |

Each of those has an optional per-axis override, so the two axes need not share a
size or a weight. Support for overrides does not remove the recommendation to
keep X/Y axis-label sizes equal:

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

The generic fallback family is DejaVu Sans at normal weight — chosen because it ships with matplotlib,
so a fresh checkout can render without font installation. This is not a general
serif/sans-serif policy. Ordinary default text is upright; mathtext handles maths variables.
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

Category ticks default to a 30-degree rotation from the profile. Overlap checks
respect the text rotation. After layout, a fitting rotated-bar Y title is shifted
within its allocated panel's vertical bounds; font sizes and data limits stay
fixed. Impossible fits remain visible to the clipping check.

## Legends

`legend.placement` selects `inside` (default) or `outside`; an older profile
without this field retains `inside`. Inside mode uses the per-panel legend
settings below. Outside mode reserves one framed area for the entire figure,
using `legend.side` (`top`, `bottom`, `left`, or `right`). The browser offers
native radios for inside/outside mode, then exactly four side radios in outside
mode. New configurations default to bottom. Honor an explicitly chosen side;
report insufficient space instead of silently moving it. Older outside profiles
without `side` retain their previous automatic right-then-bottom behavior (`auto`).
The figure's existing canvas width and height include this area. Text, markers
and strokes retain physical sizes; neither data nor the whole exported figure
is rescaled. If the selected placement does not fit, report a recoverable size error.

The outside legend covers line/scatter series, including single-series panels
because the user explicitly requested a separate legend. Repeated entries merge
only if both their names and drawn styles agree. Equal names with different
styles retain separate entries labelled by source-panel position. Bars use named
categories on their axis and add no series legend. In mixed grids, line/scatter
entries still share the one outside area. Legend font size/weight, handle length,
spacing and columns come from the profile; outside mode always draws a frame.

The browser composes a separate SVG legend using the same glyphs/series styles
as the charts. Python uses a figure-level legend and constrained layout's
`outside` placement ([Matplotlib documentation](https://matplotlib.org/stable/api/_as_gen/matplotlib.figure.Figure.legend.html)).
Their layout solvers can differ in spacing, but must preserve an explicit side.
Legacy automatic mode can choose different sides in borderline cases. The shared
semantics and physical size are the contract, not pixel equivalence.

In inside mode, `legend.show_for_single_series` is `false`: a one-series line chart names its data
in the y label and the caption, so a legend would only take space. Two or more
series always get a legend — the `legend_present` check fails otherwise.

Inside placement is `"best"`, which minimises overlap with the data but does not
guarantee it. The browser adds `panel_N.legend_data_overlap`: it
checks actual data strokes and marker shapes against the legend's layout
rectangle, at 288 dpi in physical units, before the legend covers them. Stroke
width, dash gaps and plot clipping are respected; the legend's own handles and
chart gridlines are excluded. The rectangle remains a protected reading area
with or without an opaque frame. A warning locates the affected panel/legend and
suggests more figure space or smaller legend text. It does not move the legend
or alter data automatically. Finite raster sampling is not a proof of clearance;
visual review remains necessary. Python's report does not run this browser check.

## What the checks can and cannot tell you

Exact and trustworthy:

* canvas size, PDF page size, PNG pixel size;
* expected axes count (one for a single panel, or the declared rectangular grid);
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
* whether the Python-rendered legend covers data (the browser performs its own
  geometric check described above).

`visual_review` is therefore always `not_checked`. Nothing in the pipeline fills it
in. Only a person or an agent that actually opens `figure.png` can close it, and if
that is impossible in the environment, the honest report is that the visual review
did not happen.

Rectangular grids use the same physical type and line sizes on a shared canvas.
Their plot-area check is relative to each allocated cell, and they additionally
check overlaps between panel decorations. Wide profiles can span columns.

## Deliberately out of scope in this version

The bundled renderer does not implement nonrectangular panel layouts,
histograms, heatmaps, 3D charts, stacked/grouped bars, twin axes, error bars or log
axes. It supports line/bar/scatter, rectangular grids and conference reference
profiles. The descriptive skill constraints can guide other renderers without
implying that these bundled checks verified their outputs.

## Background reading

These informed the approach; none is a dependency.

* tueplots — figure sizing for papers: https://github.com/pnkraemer/tueplots
* Matching figure size to a LaTeX document: https://jwalton.info/Embed-Publication-Matplotlib-Latex/
* `savefig` reference: https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.savefig.html
* Paul Tol's qualitative colour schemes: https://sronpersonalpages.nl/~pault/
