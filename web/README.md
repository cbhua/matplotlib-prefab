# The browser style lab

Version **0.5.0** uses native HTML/CSS paper layout and browser SVG charts with
Matplotlib text outlines. Both run entirely in the browser. Static hosting needs
no Python backend, Pyodide or LaTeX. Offline Python tooling builds the glyph atlas;
the historical render API and Pyodide worker remain in the repository for reference.

## Workflow

Choose **Template, panel grid and Single/Double Column** on one setup page,
then Create figure. Panels start as line plots; select a panel and change its
example or import data in the right sidebar. A compact assessment sits above Hand off, which offers a single **Copy for Agents**
action containing the full spec, profile, dimensions and reproduction instructions.
Figure content, physical size and shared styles follow. Zoom stays centered immediately above the paper. The initial zoom fills the available preview width (the tall page scrolls); manual zoom is
retained across redraws. On desktop, the workspace uses the centered 60% of the
window (with width bounds for readability), expanding on smaller screens.
Font weights use four discrete stops; numeric controls have stepped sliders and
precise number inputs. Template labels omit years while internal preset IDs stay stable.

| Preset | Single Column | Double Column |
| --- | --- | --- |
| ICLR 2026 | 69.85 mm, half body width, right float with text wrap | 139.70 mm |
| NeurIPS 2026 | 69.85 mm, half body width, right float with text wrap | 139.70 mm |
| ICML 2026 | 82.55 mm, one article column | 171.45 mm, spanning both columns |

**Figure size** exposes only width (30 mm up to the template body width) and
height (10–180 mm). These change the SVG and its paper slot together, independently,
without scaling font sizes. The template body font, leading, caption and margins
are locked in the UI. The main tool renders only the first page: excess example
prose is omitted, and oversized content is clipped to the sheet. Standalone
reflow/reference demos retain their original behavior.

## Figure assessment and examples

The candidate list contains line/bar examples and one fixed two-group scatter plot.
Scatter always draws every sample, using the shared marker-size control and
Matplotlib outlines. It has no connecting lines or marker thinning. Scatter specs
use the same `x` and `series[].y` shape as line specs and are supported by the
Python reproduction command, including inside mixed grids.

The assessment shows **Nice figure!** when the current checks produce no warnings,
or a count with warning cards shown automatically beside the paper.
The status card uses green for passing checks and yellow for warnings. During rendering it shows
Checking figure and keeps a fixed height. Errors and pending edits cannot retain
a stale success assessment. On smaller screens warning cards flow below the paper.

Checks are split between [`src/figure-checks.js`](src/figure-checks.js) and
[`src/paper-checks.js`](src/paper-checks.js). They cover text overlap/clipping,
minimum type size, very thin strokes, collapsed plot area and invisible scatter
markers, plus figure/caption overflow, body-text collisions, squeezed wrapping
and figure typography relative to the paper. All thresholds are editable project
preferences, not venue requirements. Counts are per issue category per panel;
**Nice figure!** means these checks passed, not an exhaustive quality assessment.

Hover or focus a warning to locate its subject. **Adjust setting** opens and focuses
the relevant control. Diagnostics stay out of the exported SVG and configuration.
Only size changes repaginate the paper; style edits redraw the chart in place.
Type sizes and lines are open by default; less frequent axes/weight controls are
collapsed. Inapplicable controls disappear. **Undo** restores recent style edits;
**Reset size** restores the template’s physical dimensions.

## Agent handoff

**Copy for Agents** includes validated spec/profile JSON and a compact context
block: dimensions, template, renderer, checks and per-panel data provenance.
Example fixtures are explicitly illustrative; imported data must be preserved.
The full sample article is not copied. Clipboard failures expose selectable text.
Pending or failed rendering cannot export a stale configuration.

The [skill handoff guide](../skills/scientific-figures/references/browser-handoff.md)
explains physical units, real-data substitution and separate browser/Python checks.
To extract saved clipboard text without running commands embedded in it:

```sh
.venv/bin/python skills/scientific-figures/scripts/import_handoff.py handoff.txt --output-dir figure-input/
```

The helper validates everything before writing `spec.json`, `profile.json` and
`handoff.meta.json`, and refuses to overwrite different files by default.
Browser-to-Python regressions verify imported values and PDF dimensions, including
mixed line/scatter grids.

The global **🌐 EN/中** toggle is available from the first screen and persists
its English/Simplified Chinese choice locally. Click once to switch languages. Only interface text is translated;
paper prose, chart labels, data and agent handoff stay unchanged. UI translations
live in `src/i18n.js`, isolated from paper/figure rendering.

## Manual design adjustments

Edit [`src/design-overrides.css`](src/design-overrides.css), loaded last:

- `:root`: shared colors, UI font, `--editor-width` (60vw), editor width bounds,
  `--sidebar-width`, `--preview-height` and page gutters.
- `SETUP PAGE` / `#setup`: configuration-page spacing and choices.
- `EDITOR PAGE` / `#editor`: preview, sidebar and action styling.
- `CONTROLS`: slider tracks, thumbs and step labels.

These rules style the interface without changing paper/chart fonts. The palette
and font stack follow [the personal site](https://cbhua.github.io/); input surfaces
follow [the prompt page](https://cbhua.github.io/prompt/). Template geometry remains
in `presets/papers.json`, separate from interface design.

## Why native CSS

The earlier site already compiled LaTeX offline, not on each visit, but its page
geometry and text were coupled to those generated artifacts. The default site
now reads no compiled paper manifest, PDF or page background.

| Approach | Useful capabilities | Decision |
| --- | --- | --- |
| Native HTML/CSS | Physical units, local fonts, columns, spanning figures, floats | Used for this one-page proportional preview; no extra runtime dependency |
| Paged.js | Browser pagination and CSS paged-media support | Consider if we add complete multi-page papers |
| Vivliostyle Viewer | HTML/CSS document typesetting and document viewing/printing | Consider for richer full-document preview |

References: [CSS multicol and breaks](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Multicol_layout/Handling_content_breaks),
[column-span](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/column-span),
[float](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/float),
[@font-face](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@font-face),
[Paged.js documentation](https://pagedjs.org/en/documentation/),
[Vivliostyle Viewer documentation](https://docs.vivliostyle.org/en/viewer/vivliostyle-viewer/).

This is not a LaTeX-equivalent page. Hyphenation, justification, pagination and
float placement can differ. CSS uses 72 points per inch, while TeX points differ
slightly. Screen millimetres are logical units, not a ruler measurement of the
monitor; zoom preserves the ratio between text and figure. Prose and captions
are illustrative. Figure styles remain provisional choices, not conference rules.

## Customize or add a preset

Edit `presets/papers.json`. Each preset defines a unique ID, name/year, one or two
article columns, paper and body rectangles in mm, column gap, packaged font
family, type/spacing defaults and figure aspect ratio. The setup cards derive
from this catalog automatically. Narrow means half body width with text wrap
for one-column articles, or one article column for two-column articles. Wide
means full body width. No LaTeX build is needed after changing this file.

`src/css-paper.js` validates the catalog, calculates physical slots and builds
semantic HTML. `src/css-paper.css` supplies the layout; `src/paper-prose.js`
contains the sample text. Fonts are self-hosted through the existing fonts
manifest and `@font-face`. Adding a different font requires packaging that font
and declaring it in the manifest. Nimbus faces and their licence are in
`public/generated/fonts/`.

The default figure pipeline is `outline-renderer.js` → `native-chart.js`.
It uses the same spec/profile fields as the Python CLI, with offline glyph and
marker paths in `chart-demo/text-outlines.json`. Separate X/Y sizes and weights,
line/bar/scatter settings and mixed grids are supported. Each panel gets an equal cell;
font and stroke sizes retain their physical units. Text clipping/overlap warnings
are browser checks, not the Python inspection report. Tight grids can require a
larger canvas. General Matplotlib constrained layout is not replicated. The browser’s best-legend
heuristic chooses the least occupied of four corners using data points; it is not
Matplotlib’s full overlap solver.

Fixed example labels have whole-run outlines; other printable ASCII labels use
packaged glyphs and kerning pairs. Unsupported Unicode gives a clear render error;
add those labels to `build_chart_glyphs.py` and rebuild to support them. Generated
SVGs contain paths and require no fonts. Configuration exports retain a Python
reproduction command for the same data/style, but identify the browser renderer
and do not promise identical Python layout. The main interface focuses on copying the complete configuration for an agent. Paper configuration remains separate under `paper_preview`.

## Run and deploy

The checkout includes packaged fonts and renderer assets. With the uv environment:

```sh
.venv/bin/python scripts/build_web_assets.py
.venv/bin/python web/serve.py             # http://127.0.0.1:8765/index.html
```

For a minimal local static server use:

```sh
.venv/bin/python web/serve.py --static-only
# Optional offline glyph rebuild (also used by chart-demo.html):
.venv/bin/python scripts/build_chart_glyphs.py
```

Deploy `web/` to a static host, including the glyph atlas, presets, reference prose
and packaged paper fonts. No `fetch_pyodide.py` step is needed. The main page never
calls `/api/renderer` or `/api/render`.

`build_fonts.py` is an optional font rebuild tool tied to the historical font
calibration inputs; it is unnecessary for ordinary preset editing or hosting.
No deployment has been performed.

## Verification and historical references

```sh
.venv/bin/python -m pytest tests/web/test_css_paper.py tests/web/test_text_wrap.py tests/web/test_setup.py tests/web/test_browser.py tests/web/test_controls.py tests/web/test_web_assets.py
.venv/bin/python -m pytest tests/test_grid.py tests/test_import_handoff.py
```

Browser tests check all six layouts, font availability, physical slot ratios,
text wrap, working without compiled conference assets, locked template typography,
independent figure dimensions and a single rendered preview page. They also cover
the compact setup workflow, weight sliders and existing figure controls. Playwright Chromium is required.

`src/paper-page.js`, compiled conference artifacts and `tests/web/calibration/`
are retained as historical exact-page references. Their existing fingerprint
reports are not evidence for the new CSS preview. The old
`build_and_verify_web.py` exact-page workflow and its calibration assertions are
not the acceptance suite for this proportional preview; they have not been
regenerated or relaxed to claim equivalence.

## Fixed-content page experiment

Open **`reference.html`** directly to compare a complete
ICML narrow reference page with its frontend reproduction. The comparison modes
are Frontend, LaTeX reference, Side by side, Overlay and Difference. The original
body, caption, bibliography, header and folio are retained, including the empty
figure placeholder that exists in that baseline.

This experiment addresses a different scope from automatic CSS reflow: **one
fixed page can retain its exact line breaks and text origins**. `fixed-paper.js`
uses ordinary positioned HTML text and the packaged Nimbus faces. A zero-height
inline marker measures each HTML baseline after fonts load. Text is never stretched
to the expected width. Only Computer Modern math fragments use the existing
vector outlines. There is no PDF renderer, TeX or Pyodide dependency at runtime.
The original PDF supplied layout measurements once, offline; the site reads static
JSON thereafter. This does not implement TeX's paragraph-breaking algorithm for
arbitrary edited prose.

The original page manifest missed two stroked paths: the running-head rule and
the radical overbar. `reference/icml2026-narrow.json` supplies those measurements;
the regression checks them independently against the PDF content stream. No
historical baseline or old calibration report was modified.

Run the live regression and produce review images/report:

```sh
.venv/bin/python scripts/verify_fixed_page.py
.venv/bin/python -m pytest tests/web/test_fixed_page.py
```

The first command writes `.tmp/fixed-page-regression/{browser,overlay,difference}.png`
and `report.json`. It freshly extracts all text and geometry from the original
PDF and compares a Chromium screenshot at 150 DPI to the committed PDF raster.
Neither LaTeX nor Poppler is needed to rerun it. Text origins/baselines/slot edges
must be within 0.03 mm, native widths within 0.05 mm, and font sizes within 0.01 pt.
The visual check measures **ink**, separately for header, caption, prose, formula,
bibliography and folio. It permits a one-pixel rasterizer edge tolerance, at most
5% unmatched ink in either direction and an ink-mass ratio of 0.85–1.15. No image
registration, scaling, figure masking or whole-page whitespace score is used.
The tests deliberately shift text, replace its font, change its size and remove
references, the header rule or folio to verify that real regressions fail.

A passing result means this fixed reference meets those measured tolerances in
the tested Chromium version, not that two different rasterizers emit identical
pixels or that arbitrary paper content will reflow identically to TeX.

## Dynamic figure height and text reflow

Open **`reflow.html`** directly or from the fixed-reference page. This ICML
experiment keeps the reference's physical columns, local font sizes/leading,
running head and folio, while allowing browser line breaks to change. Adjust
figure height (10–180 mm), switch between one-column and spanning width, or edit
the caption, body and bibliography. Local image upload accepts raster images
and SVG; images retain their aspect ratio inside the adjustable frame. Frame
height is the layout allocation, not a promise to stretch an uploaded image.

`reflow-paper.js` measures actual HTML paragraphs and splits them at word
boundaries into explicit columns. Text moves from the left column to the right,
then to additional pages, with sequential folios. Spanning figures reserve space
above both first-page columns. Headers and fonts keep the fixed reference's
measurements. No paragraphs are hidden, discarded or scaled to fit. Oversized
figure/caption combinations display an error and retain the last valid layout.
Headings stay with space for following text; paragraph fragments preserve inline
italics, and bibliography entries retain hanging indents.

`reference/reflow-content.json` stores semantic versions of the same fixed-page
body and bibliography: line-end hyphens are removed and inline mathematical
symbols use plain Unicode in this editable prototype. Blank lines separate
paragraphs; `## ` starts a heading. Editing references uses plain text, while
Reset page restores the original italic spans. This is approximate browser
pagination, not a TeX interpreter or a general LaTeX source editor. The fixed
reference reproduction remains available unchanged.

Height and text edits use browser layout only: no backend, Pyodide or external
requests. Resize work is scheduled per animation frame. Regression tests exercise
short/tall figures in both widths, pagination and backflow, complete content
preservation, unchanged type sizes, non-overlap, editing, upload and invalid
settings:

```sh
.venv/bin/python -m pytest tests/web/test_reflow.py tests/web/test_fixed_page.py
```

## Main-tool integration tests

```sh
.venv/bin/python -m pytest tests/web/test_integrated_layout.py
```

These exercise all three venues and both widths through the browser renderer (with separate compatibility checks for the historical
local API), short/tall/backflow transitions, SVG dimensions, exported physical sizes,
mathematics-free example prose, grids and text-only edits without render calls.
The original fixed-page fixture deliberately retains its original maths so its
LaTeX regression oracle stays intact.

## Independent frontend chart demo

Open **`chart-demo.html`** to try plotting without a Python backend or Pyodide.
This comparison remains separate; the main tool now uses its outline rendering approach.

`src/native-chart.js` builds SVG paths, markers, signed bars, axes, ticks, labels
and a legend directly from the same fixed line/bar specs and style profile.
The SVG viewBox uses points and its outer dimensions use millimetres. Resizing
recomputes coordinates while retaining physical type and stroke sizes. The demo
supports width/height, shared tick/legend type, axis-label type (one point larger),
data line width, markers and bar category rotation. It is a single-panel
prototype, not an implementation of every Matplotlib/profile feature: no grid
charts, general legend placement, mathtext or full constrained-layout solver.
The fixed line example selects the upper-right corner; best placement can choose
a different corner for other data.

Ten frozen Matplotlib SVGs cover both chart types at default, tall, wide,
large-type and thicker-line settings. The browser does not use their coordinates
to draw its own chart. Text defaults to **Matplotlib outlines**: an offline atlas
contains the exact DejaVu Sans text paths, advances and font metrics for the fixed
labels and tick vocabulary. JavaScript scales and places these paths at runtime;
no Python is involved. Baselines, legend spacing and marker paths also follow the
reference renderer. **Browser text (previous)** remains selectable for comparison,
using the matching locally packaged font (with its licence). Outline exports are
font-independent but their letters are paths, not editable SVG text; browser-text
exports embed the font. Printable ASCII labels can also be composed from packaged glyphs and kerning;
other new characters require rebuilding the outline atlas.
All reference files are preloaded;
controls and comparison switches make no further requests. Python is needed only
to rebuild the references, not to view or interact with this demo.

Side-by-side, overlay and difference views compare identical inputs. After a
custom edit, the reference is visibly marked as a different configuration and
overlay/difference modes are disabled until reset. Text clipping and overlapping
category labels produce warnings; even the large-type Matplotlib comparison case
can be crowded, so the demo does not silently shrink type to hide it.

```sh
# Optional, offline regeneration of reference SVGs and the packaged font:
.venv/bin/python scripts/build_chart_demo.py
# Rebuild fixed text/marker outlines without changing reference charts:
.venv/bin/python scripts/build_chart_glyphs.py
# Browser tests; no backend / Pyodide needed:
.venv/bin/python -m pytest tests/web/test_native_chart.py tests/web/test_chart_text_fidelity.py
# Capture both renderers and measure their plot bounds:
.venv/bin/python scripts/verify_native_chart.py
```

The latter writes `.tmp/native-chart/report.json` and review PNGs. Tests reconstruct
all line data values from the SVG coordinates, check signed bars against zero,
verify physical canvas/type/stroke units and exports, block API/Pyodide requests,
and compare axes rectangles with the frozen Matplotlib SVGs to within 0.03 mm.
Separate text regressions rasterize selected labels from the original reference
SVGs and both text modes at identical positions at DPR 1, 2 and 3. They require
outline pixel error below 1% of reference ink and ink-mass difference below 0.5%;
reports are saved as `.tmp/native-chart/text-fidelity-dpr*.json`. These are isolated
label checks, not a claim of whole-chart pixel equivalence. The geometry report
includes actual browser draw times. Matplotlib documents its default SVG
[text-as-path approach](https://matplotlib.org/stable/users/explain/text/fonts.html).

Native SVG was chosen for this small, fixed-data experiment: its
[viewBox and physical viewport](https://developer.mozilla.org/en-US/docs/Web/SVG/Reference/Element/svg)
make the print dimensions explicit. [D3 axes](https://d3js.org/d3-axis) are an
alternative if future scope warrants a larger scale/axis toolkit; this demo adds
no charting-library dependency.

## Space-use review

`src/figure-density.js` estimates spatial occupancy inside each panel’s plotting
rectangle, independently of screen zoom. It is not a measure of scientific
information or importance. The 48 × 36 grid reserves 3 mm around visible data
lines, markers, bars and legends; axis/grid ink does not disguise empty space.
A histogram scan finds the largest contiguous empty rectangle.

All conditions must hold to warn: plotting area ≥ 5,000 mm²; ≥ 65% unoccupied;
largest empty rectangle ≥ 24% of the plot and ≥ 1,800 mm², with both sides ≥ 20 mm.
This exempts compact panels and protects ordinary breathing room. Thresholds are
project heuristics in `DENSITY_RULES`, not venue rules. Intentional empty regions
can still trigger a suggestion; users retain control of dimensions and data.
Warnings include measured occupancy/region geometry in the agent handoff. Hover
or focus highlights the empty region; **Adjust setting** targets width or height.

## GitHub Pages deployment

The repository includes [`.github/workflows/pages.yml`](../.github/workflows/pages.yml).
It publishes the contents of `web/` after a push to `main` that changes the website
or workflow; **Actions → Deploy GitHub Pages → Run workflow** also publishes manually.
No npm, uv, Matplotlib or LaTeX installation is needed in CI. The checked-in glyph
atlas, presets, generated specs/profiles, font files and their licences are the
site's deployable assets. Commit new/updated assets along with the source code.
The workflow excludes local Python servers, caches and the historical Pyodide
runtime; the small `pyodide.lock.json` is still read as historical metadata.
The standalone reference/reflow/chart demos remain available.

One-time GitHub setup:

1. Push the project, including `web/` and `.github/workflows/pages.yml`, to `main`.
2. Open **Settings → Pages → Build and deployment → Source → GitHub Actions**.
3. Run the workflow from **Actions** (or push another website change).
4. Open the URL shown by the successful `github-pages` deployment.

For the current `cbhua/matplotlib-prefab` repository, the expected default URL is
**https://cbhua.github.io/matplotlib-prefab/**. Keep the trailing slash. Project-relative
asset URLs work under this prefix as well as at a domain root. No custom domain,
`CNAME`, repository secret or `gh-pages` branch is required. The existing personal
homepage stays separate. A custom domain configured on the account's Pages site
can change the final project URL; use the deployment's reported URL in that case.

Pages must be enabled for the repository, and repository/organization Actions
policies must permit the official `actions/*` actions and the workflow's
`pages: write` / `id-token: write` deployment permissions. Public repositories work
with GitHub Free; private repository availability depends on the GitHub plan.
See [GitHub's custom Pages workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
