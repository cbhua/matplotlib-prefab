---
name: scientific-figures
description: Render a publication-style single-column, single-panel line or bar chart from data with matplotlib, at a fixed physical size, then check the result. Use when someone asks for a figure, chart, plot or graph for a paper, report or thesis, or wants an existing figure redone at a consistent size with legible labels. Covers line charts (one shared x, one or more named series) and vertical bar charts (one value per named category). Not for scatter, histogram, heatmap, 3D, multi-panel or two-column figures.
---

# Scientific figures (single column, single panel)

Turns tabular data into an 85 mm wide, single-panel line or bar figure: a PDF at a
fixed physical size, a PNG preview, a snapshot of the input, the resolved style
profile and a check report.

**The style numbers are provisional.** They are the project's initial choices, not
a journal or conference requirement. Never present them as a venue standard.

## Scope

Handled: line charts (one shared numeric x, one or more named y series) and
vertical bar charts (one numeric value per named category, negatives allowed).

Not handled — say so plainly rather than improvising: scatter, histogram, heatmap,
3D, box/violin, stacked or grouped bars, twin axes, error bars, log axes,
multi-panel and two-column layouts. A bar chart here compares named categories; it
does not bin raw samples, so a request for a distribution is a histogram request
and is out of scope.

## Workflow

### 1. Write the spec

Put the user's data into one JSON file. Read `references/input-schema.md` for the
exact fields, and read it before writing the first spec of a session — the
validator rejects unknown fields, so guessing costs a round trip.

Restructuring data (a CSV column into `x`, a column per series) is fine.
Reordering, smoothing, resampling, rounding or dropping points is not: the figure
must show what the user gave you. If the data genuinely cannot be plotted — gaps,
`NaN`, mismatched lengths — say so and ask, rather than patching it silently.

Keep the spec somewhere durable (next to the output, or in the user's project),
not in a temporary directory — it is how the figure gets regenerated later.

### 2. Render

```sh
python skills/scientific-figures/scripts/render.py \
    --spec <your-spec>.json \
    --output-dir <where-the-figure-should-go>
```

Worked examples of the input live in `../../tests/data/`, and what a render
produces is committed under `../../tests/output/`.

Add `--profile <path>` to use an edited style profile. Paths are relative to
wherever you run the command; the script itself works from any directory.

Exit codes: `0` the figure rendered (possibly with warnings), `1` a check failed,
`2` the spec or profile was rejected and nothing was written.

If it exits `2`, the message names the field and the reason. Fix the spec — do not
work around the validator by changing the data.

### 3. Read the report

`report.json` and the terminal summary carry one entry per check, each `pass`,
`warn`, `fail` or `not_checked`. Read the failures and warnings; do not skim to the
overall status.

Common ones and what they mean:

| Check | If it complains |
| --- | --- |
| `glyph_coverage` | The font lacks characters in the labels (e.g. CJK in DejaVu Sans). Set `fonts.family`/`fonts.fallbacks` in a profile copy to a font that covers them. Do not ship a figure with box glyphs. |
| `font_resolution` | The requested font is not installed and matplotlib substituted one. Install it or change the profile. |
| `text_within_canvas` | Labels are being clipped. Shorten the label, rotate bar categories via `bar.category_label_rotation_deg`, or widen `canvas.width_mm`. |
| `tick_label_overlap` | Tick labels collide. Lower `axes.max_xticks`, rotate, shorten, or widen. |
| `panel_area` | Decorations are crowding out the plot. Usually too many series or overlong labels. |
| `line_data_integrity`, `bar_category_order` | A real bug — the drawing does not match the input. Stop and investigate; do not ship it. |

### 4. Actually look at the PNG

`visual_review` always comes back `not_checked`, and nothing fills it in
automatically. Open `figure.png` and judge what no script can:

* is every label legible at final size (the PNG is ~4× the printed size)?
* does the legend sit clear of the data?
* are the series separable by colour *and* by marker/dash?
* is the panel crowded, or is there dead space?

If the environment cannot display images, say explicitly that the visual review did
not happen. Never report it as passed.

### 5. Fix and re-render

Fix what the report and your own look at the PNG turned up, then re-render. **At
most two correction rounds**, then report what is still wrong. Never edit the
user's data to make a check pass, and never loop.

Style fixes go in a *copy* of the profile passed with `--profile`, or — if the user
wants the change to be the new default — in
`references/profiles/single-column.json` itself, with their agreement. Never
hard-code a size or colour in a template.

### 6. Hand over

Report where the files are, which checks warned, whether you looked at the PNG, and
the reproduce command from `report.json`.

## Output

The output directory gets exactly five files. Anything else already there is left
alone; nothing is deleted.

| File | What it is |
| --- | --- |
| `figure.pdf` | The deliverable, at the profile's physical size (85 mm wide by default) |
| `figure.png` | Raster preview at `output.png_dpi` (300) |
| `spec.json` | The validated input, exactly as drawn |
| `profile.resolved.json` | The style profile that produced this figure |
| `report.json` | Check results, environment (matplotlib version, resolved fonts), reproduce command |

`spec.json` + `profile.resolved.json` reproduce the figure; `report.json` carries
the command that does it.

## Style

All style lives in `references/profiles/single-column.json` — sizes, fonts,
colours, tick counts, bar width, output settings. Templates read it and hold no
defaults of their own.

Point sizes are physical: a 9 pt label is 9 pt on the page, and `png_dpi` only
changes preview resolution. Read `references/design-rules.md` before changing a
value, arguing for one, or explaining the visual choices — it covers the palette,
the marker/dash strategy, the layout engine constraint, and exactly what the checks
can and cannot prove.

## Requirements

Python with `matplotlib` and `numpy`. **No LaTeX installation is needed** — maths
labels use matplotlib mathtext (`"$\\alpha_i$"`). See `references/input-schema.md`
for the maths and non-ASCII text rules.

## Files

* `scripts/render.py` — CLI: validate, draw, export, check
* `scripts/inspect_figure.py` — the checks; also runnable standalone on an existing
  output directory (`--output-dir`) for file-level re-checks
* `scripts/figure_core.py` — spec/profile validation, style resolution, export
* `assets/templates/line.py`, `assets/templates/bar.py` — drawing only
* `references/input-schema.md` — the input contract
* `references/design-rules.md` — the design decisions and the limits of the checks
* `references/profiles/single-column.json` — every style value

Outside the skill, `tests/data/` holds prefab specs and `tests/output/` holds their
rendered results — a proof sheet of the current profile, regenerated by
`python tests/render_gallery.py`. Look there when you need a worked example of the
input format or want to see what the preset values actually produce.
