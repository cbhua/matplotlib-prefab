---
name: scientific-figures
description: Render publication-style matplotlib line, bar and scatter figures, including rectangular grids exported from the conference style lab, at a fixed physical size. Use for paper, report or thesis plots and for reproducing browser-selected figure configurations. Checks dimensions, typography and data integrity. Does not cover heatmap, statistical estimation or arbitrary panel layouts.
---

# Scientific figures

Turns tabular data into line/bar/scatter figures or rectangular grids: a PDF at a
fixed physical size (85 mm wide by default), a PNG preview, a snapshot of the input, the resolved style
profile and a check report. When actual paper placement is requested, it can
also set that figure into a real conference body page using the separate
article-context workflow.

**The style numbers are provisional.** They are the project's initial choices, not
a journal or conference requirement. Never present them as a venue standard.

## Scope

Handled: line and scatter charts (one shared numeric x, one or more named y series), and
vertical bar charts (one numeric value per named category, negatives allowed),
and rectangular grids of these charts with a shared style profile.

Not handled — say so plainly rather than improvising: histogram, heatmap,
3D, box/violin, stacked or grouped bars, twin axes, error bars, log axes,
nonrectangular panel layouts. Single-panel and grid canvases can use the measured
wide profile, including ICML’s cross-column width. A bar chart here compares named categories; it
does not bin raw samples, so a request for a distribution is a histogram request
and is out of scope.

## Workflow

### Browser grid exports

For a hand-off with `spec.kind: "grid"`, retain its `rows`, `columns`, and
row-major `panels` array. Read the grid section of `references/input-schema.md`.
The ordinary `render.py --spec ... --profile ... --output-dir ...` command
produces one combined PDF/PNG, using the Python grid renderer. The browser uses SVG layout with matching physical style units.
Canvas dimensions describe the whole grid; type sizes remain physical points
and are shared by every panel. Read the panel-specific checks as well as the
global overlap check. Dense grids may warn even when rendering succeeds.

The conference evaluator's spec input remains single-panel. To evaluate a grid,
pass its rendered directory to `scripts/evaluate_context.py --figure-dir <out>`
with the venue, layout and fixture paths from `references/article-context-evaluation.md`.
Do not run the fixed `line-multi` example as evidence for the user's grid.

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

### 4b. Receive a browser handoff

Read [references/browser-handoff.md](references/browser-handoff.md) when the user
pastes **Copy for Agents** output or asks to reproduce browser-selected settings.
Preserve the selected physical dimensions and style. Distinguish illustrative
example data from imported user data before drawing. The handoff contains the
profile, spec, data provenance, print-size target and current checks.

The main tool at `web/index.html` is a static HTML/CSS paper preview and native
SVG figure renderer using offline Matplotlib glyph outlines. It needs neither
LaTeX nor Python/Pyodide at runtime. Template typography is fixed, and only the
first illustrative page is shown. Browser and Python layout can differ; repeat
checks with the chosen output renderer and actual data.

```sh
python web/serve.py --static-only
```

### 5. Check it in a real article page

A figure is read at whatever width the template gives it, not at 85 mm on white.
Half of ICLR's text block is 69.85 mm; one ICML column is 82.55 mm. An 85 mm
figure dropped into the ICLR slot shrinks by 0.82, and its 9 pt labels print at
7.4 pt. `report.json` cannot see any of that.

```sh
python tests/render_conference_context.py --venue iclr2026 --case line-multi
```

That compiles the venue's own style around a page of real prose, places the
figure, and writes `page.pdf`, `page.png` and `context-report.json` under
`tests/output/conference-context/<venue>/<case>/`. Read
`references/article-context-evaluation.md` before running it or reporting what it
found.

**When to do this:**

* The user requests actual article placement/LaTeX verification and names a venue
  with fixtures (ICLR 2026, NeurIPS 2026, ICML 2026): produce that venue's page.
* When refreshing the compiled reference sheet, run its whole matrix, `--all`.
  Ordinary browser style selection does not require a LaTeX calibration rebuild.
* For a standalone figure request without article placement, deliver the figure
  and print-size checks; do not invent a venue requirement.

The default path re-renders the figure at the template's width, so it lands at
scale 1 and the type sizes are the ones you set. Placing an already-rendered
figure (`--figure-dir`) reports the real reduction instead.

Then **look at `page.png`** with the prose beside it: are the tick labels
readable next to 10 pt body text, is the legend clear of the data at this width,
are the series still separable? A high-DPI preview stretched to your screen is
not the printed size — the physical numbers are in the report, and `page.pdf` at
100 % is the real thing.

Needs LaTeX and poppler; `render.py` does not.
`python tests/render_conference_context.py --check-dependencies` says whether
they are installed. **If they are missing, or the fixtures are not there, say the
context evaluation did not run.** The figure itself is still deliverable — but do
not report the article context as verified when nothing compiled.

The context output goes in its own directory and never touches the five files
from step 2; `report.json` keeps the standalone check results.

### 6. Fix and re-render

Fix what the report and visual inspection found within the user's authorized
scope, then re-render. Stop repeating checks once they pass unless new changes
justify another run. Report unresolved constraints rather than changing data to
make a check pass.

Style fixes go in a *copy* of the profile passed with `--profile`, or — if the user
wants the change to be the new default — in
`references/profiles/single-column.json` itself, with their agreement. Never
hard-code a size or colour in a template.

When article placement is in scope, figure changes also require checking that placement again.

### 7. Hand over

Report where the files are, which checks warned, whether you looked at the PNG, and
the reproduce command from `report.json`.

If step 5 ran, say which venue's page you produced, the width it was placed at,
the scale factor, and that the style values are provisional project choices — not
that venue's requirement. If step 5 did not run, say so and why.

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

Most type settings have an optional per-axis override — `fonts.size_x_label_pt`,
`fonts.size_ytick_pt`, `fonts.weight_x_label` and so on — which falls back to the
shared field (`size_axis_label_pt`, `size_tick_pt`, `weight`) when absent. A
profile written before those existed renders exactly what it always did. Ask
`figure_core.font_size(profile, role)` / `font_weight(profile, role)` rather than
reading a field directly; those are what the renderer uses.

Point sizes are physical: a 9 pt label is 9 pt on the page, and `png_dpi` only
changes preview resolution. Read `references/design-rules.md` before changing a
value, arguing for one, or explaining the visual choices — it covers the palette,
the marker/dash strategy, the layout engine constraint, and exactly what the checks
can and cannot prove.

## Requirements

Python with `matplotlib` and `numpy`. **No LaTeX installation is needed** to draw
a figure — maths labels use matplotlib mathtext (`"$\\alpha_i$"`). See
`references/input-schema.md` for the maths and non-ASCII text rules.

The step 5 article-context check is the one exception: it needs `latexmk`,
`pdflatex`, `bibtex` and `pdftoppm` (`sudo apt install
texlive-latex-recommended texlive-fonts-recommended texlive-latex-extra latexmk
poppler-utils`). Without them the figure still renders; the context check reports
that it did not run.

## Files

* `scripts/render.py` — CLI: validate, draw, export, check
* `scripts/inspect_figure.py` — the checks; also runnable standalone on an existing
  output directory (`--output-dir`) for file-level re-checks
* `scripts/evaluate_context.py` — places a figure in a conference template, measures
  the result, keeps the body page. Takes its fixtures by path, so a copied skill
  still works
* `scripts/figure_core.py` — single-panel spec/profile validation, style resolution, export
* `scripts/grid_core.py` — grid validation, rendering and panel-aware checks
* `assets/templates/line.py`, `bar.py`, `scatter.py` — drawing only
* `references/input-schema.md` — the input contract
* `references/design-rules.md` — the design decisions and the limits of the checks
* `references/article-context-evaluation.md` — how the in-page check works, what it
  measures, and what it deliberately refuses to judge
* `references/profiles/single-column.json` — every style value

Outside the skill, `web/` holds the browser style lab described in step 4b — its
paper pages use `web/presets/papers.json` and `web/src/css-paper.js` without a
LaTeX dependency. Historical compiled-page evidence under `tests/web/calibration/`
does not certify the current proportional preview. `tests/data/` holds prefab specs and `tests/output/` holds their
rendered results — a proof sheet of the current profile, regenerated by
`python tests/render_gallery.py`. Look there when you need a worked example of the
input format or want to see what the preset values actually produce.

`tests/output/conference-context/` holds the same figures set into real ICLR,
NeurIPS and ICML pages, regenerated by
`python tests/render_conference_context.py --all`. That is where you see what the
preset values look like at the size a reader gets them. The venue templates,
the body-text excerpt and the wrappers live in `tests/fixtures/` and
`tests/conference_context/`.
