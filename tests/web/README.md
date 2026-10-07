# Evidence for the browser tool

## Active browser editor checks

The main editor runs without Pyodide or a plotting backend. Its active regressions
cover paper/context diagnostics, warning navigation, responsive UI and drag
stability, source-data preservation, asynchronous imports, style undo, and the
Copy for Agents → skill importer → Python PDF round trip. Run:

```sh
.venv/bin/python -m pytest tests/web/test_assessment.py tests/web/test_paper_assessment.py tests/web/test_render_responsiveness.py tests/web/test_spec_validation.py tests/web/test_handoff_roundtrip.py tests/web/test_interface.py tests/web/test_interface_stability.py
```

`test_native_chart.py` and `test_chart_text_fidelity.py` independently protect
chart geometry and Matplotlib outline fidelity against frozen references.
Run root Python tests in a separate pytest command from `tests/web`, since their
`conftest` helpers use different import contexts.

## Active fixed-page regression

`test_fixed_page.py` renders `web/reference.html` and compares the original ICML
page against HTML text with frozen line breaks and local fonts. It extracts
geometry/text from the PDF on each run and compares the screenshot against the
unchanged committed 150 DPI raster. It does not depend on Pyodide, LaTeX or
Poppler. Six deliberate defects test that the comparison actually fails.

```sh
.venv/bin/python -m pytest tests/web/test_fixed_page.py
.venv/bin/python scripts/verify_fixed_page.py
```

The second command writes current measurements and overlays under
`.tmp/fixed-page-regression/`. See `web/README.md` for thresholds and scope.
The original generic CSS preview has its own `test_css_paper.py` tests.

## Historical compiled-page evidence

The reports below predate the current CSS preview. The old full calibration
pipeline does not certify it; the fixed-page experiment above has a separate,
live regression rather than relying on these historical passing reports.

Everything in `calibration/` is generated. It is committed because these checks
are slow and need a toolchain, and because a claim about millimetres should be
readable by a person rather than re-derived on trust.

Regenerate all of it with:

```sh
python scripts/build_and_verify_web.py
```

Each report carries a `repository` fingerprint of every file that could change
it. `test_verification.py` recomputes those digests and fails when they drift —
so a report can never quietly describe a version of the tool that is no longer
here. When it fails, regenerate; do not edit the test.

## What is in here

| Path | What it answers |
| --- | --- |
| `pyodide-prototype.json` | Does this repository's code run in a browser at all, how long does it take to start, and does its SVG match a local render? |
| `baselines/<venue>/<mode>/` | The compiled LaTeX page each paper page was measured from — `page.pdf`, `page.png`, `context-report.json` |
| `pages/<venue>/<mode>/` | Browser page versus that PDF: `calibration-report.json`, `baseline.png`, `browser.png`, `overlay.png`, `difference.png` |
| `page-calibration.json` | The six pages' worst per-run errors in one place |
| `render-equivalence.json` | Browser SVG versus a local render at the pinned versions, over ten style configurations, plus interaction latency |
| `export-roundtrip.json` | Exports fed back through `render.py` and compared |
| `end-to-end/` | The full page matrix: browser preview versus a LaTeX page built from the browser's own export — `browser.png`, `page.png`, `overlay.png`, `difference.png`, `page.pdf` per case |
| `browsers.json` | Which browser engines were actually run here, and which were not |

About 25 MB of it is PNGs. Every measurement is made at 300 DPI; the images kept
here are written at 150 DPI afterwards, and the colour overlays are palettised,
so the size is a third of what it would otherwise be without any measurement
depending on it. If that is still more than you want in the repository, the
images can be dropped and regenerated — the JSON reports carry every number.

## Reading the images

`overlay.png` puts the baseline in red and the browser in blue, so anything that
lines up comes out magenta-on-black and anything that does not shows as a
coloured ghost. `difference.png` is the per-pixel difference, inverted so the
page is white and disagreements are dark; for a correct page it shows glyph
*outlines* — two rasterisers disagreeing about anti-aliasing — rather than
doubled shapes, which would mean a displacement.

A whole-page similarity score is deliberately not used anywhere: these pages are
mostly white, and white agrees with white. The thresholds apply to the geometry
measured from the DOM against the PDF, and to whether shifting the whole image
would improve the match.

## Thresholds

Set in `scripts/compare_pages.py` and asserted in `test_page_manifests.py` so
they cannot be quietly relaxed to make a page pass:

| | Threshold |
| --- | --- |
| Paper size | 0.2 mm |
| Figure slot edges | 0.2 mm |
| Per-run baseline | 0.2 mm |
| Per-run left edge | 0.2 mm |
| Per-run width | 0.35 mm |
| Whole-image drift | 0.2 mm |

## Running the tests

```sh
python -m pytest tests/web -q
```

They skip with a message naming the missing command when the Pyodide runtime,
the fonts or Playwright are absent. A skipped check is not a passed one — if you
are reporting on this work, say which of them actually ran.
