# Matplotlib Prefab

An agent-facing skill for producing publication-style matplotlib figures: give it
data and it renders a line/bar figure or a rectangular grid at a fixed physical size,
then checks the result and tells you what it could not check.

The previous version of this repository — a static gallery of notebook templates —
has been removed. It remains in the git history at commit `a3f6dfb` if you need it.

```
README.md
pyproject.toml
skills/scientific-figures/   the skill: SKILL.md, scripts, templates, references, profile
scripts/                     build and verification tooling for the browser style lab
web/                         the browser style lab: a static site, no server, no LaTeX
tests/                       prefab data, the proof sheets, the conference fixtures, the tests
```

## The skill

[`skills/scientific-figures/`](skills/scientific-figures/SKILL.md) covers two chart
types:

* **line** — one shared numeric x, one or more named y series;
* **bar** — one value per named category, vertical, negatives allowed.

Each render produces a PDF at the exact physical size the profile asks for, a PNG
preview, a snapshot of the validated input, the resolved style profile, and a
report of deterministic checks — five files, and nothing else in the directory is
touched.

Scatter, histogram, heatmap and 3D remain out of scope. The browser workflow also
supports rectangular grids of line/bar panels and narrow/wide paper slots; its
exported grid specs can be reproduced with the same `render.py` command.

```sh
python -m venv .venv && .venv/bin/pip install matplotlib numpy

.venv/bin/python skills/scientific-figures/scripts/render.py \
    --spec tests/data/line-multi.json \
    --output-dir .tmp/figure-preview/line-multi
```

Input is a small JSON file — see [`tests/data/`](tests/data/) and the
[input contract](skills/scientific-figures/references/input-schema.md):

```json
{
  "schema_version": "1",
  "kind": "bar",
  "x_label": "Method",
  "y_label": "Accuracy change (pp)",
  "categories": ["Baseline", "Dropout", "Mixup"],
  "values": [0.0, -0.8, 2.4]
}
```

## Style is one file — and you can see it

Every size, colour, line width, tick count and export setting lives in
[`skills/scientific-figures/references/profiles/single-column.json`](skills/scientific-figures/references/profiles/single-column.json).
Templates draw artists and hold no defaults of their own, so editing that file
changes both chart types.

> **The values in it are provisional.** They are this project's initial choices —
> 85 mm wide, 0.618 aspect ratio, 9 pt axis labels, 8 pt ticks, 1.2 pt data lines,
> DejaVu Sans, a Paul Tol qualitative palette — not a journal or conference
> requirement. They are meant to be reviewed and finalised by hand.

To tune them, edit the profile and regenerate the proof sheet:

```sh
.venv/bin/python tests/render_gallery.py
```

That renders every prefab spec in `tests/data/` with the current profile into
`tests/output/`, and writes [`tests/output/index.md`](tests/output/index.md) — the
pictures, with the values that produced them printed above. Six cases, chosen so
that each knob shows up somewhere: single and multi series, eight series (where
colours run out and the dash pattern takes over), mathtext labels, all-positive
bars and bars crossing zero.

The rendered sheet is committed, and the test suite checks it against the profile
and the data, so it can never quietly disagree with the settings in the repository.

Point sizes are physical: a 9 pt label is 9 pt on the printed page, and the PNG DPI
only changes preview resolution. `--profile <path>` renders with an edited copy
without touching the default. The reasoning behind each value, and an honest
account of what the automatic checks can and cannot prove, is in
[design-rules.md](skills/scientific-figures/references/design-rules.md).

No LaTeX installation is required to render a figure — maths labels use
matplotlib mathtext. Only the in-page evaluation below needs one.

## But how big is it *on the page*?

A figure on a white background is not the figure a reader sees. Half of ICLR
2026's text block is 69.85 mm; one ICML 2026 column is 82.55 mm. Drop the default
85 mm figure into the ICLR slot and everything in it shrinks by 0.82 — 9 pt axis
labels print at 7.4 pt. No amount of inspecting `figure.pdf` reveals that.

```sh
sudo apt install texlive-latex-recommended texlive-fonts-recommended \
                 texlive-latex-extra latexmk poppler-utils
.venv/bin/python tests/render_conference_context.py --all
```

That compiles the venues' own unmodified style files around a page of real
running prose, sets each figure in as an ordinary float, and keeps the single
body page it landed on:
[`tests/output/conference-context/index.md`](tests/output/conference-context/index.md).

| Venue | Layout | The figure gets |
| --- | --- | --- |
| ICLR 2026 | one column, camera-ready | half the text width |
| NeurIPS 2026 | one column, camera-ready | half the text width |
| ICML 2026 | two columns, camera-ready | one whole column, not half the text width |

The width is measured by TeX inside the document, the figure is re-rendered at
that width so it lands at scale 1, and the width in the report is read back out
of the compiled page's drawing transform — not out of the `\includegraphics`
argument, which would prove nothing. Change a number in the profile, re-run,
and you can see what it does to a real page.

The compiled documents are typesetting fixtures and say so on their own title
pages. The prose is an excerpt from a published article used only as typographic
context, credited in
[`tests/fixtures/article-context/provenance.md`](tests/fixtures/article-context/provenance.md);
the plotted data is synthetic. This part is the only thing in the repository that
needs LaTeX.

## Or move the sliders yourself

The web tool starts with **Template, Panel layout and Column width** together
on one page. Create the figure, then change Line/Bar/Scatter examples or import data
for each panel in the right sidebar. You can adjust styles and physical dimensions,
and use **Copy for Agents** for the complete reproducible configuration. It shows the
figure at its target size inside a browser simulation of a conference page and lets you change the
type sizes, weights, line widths, tick counts and bar settings with the figure
redrawing as you go — then hands you a configuration an agent can reproduce.

```sh
.venv/bin/python scripts/build_web_assets.py
.venv/bin/python web/serve.py                  # http://127.0.0.1:8765/index.html
```

Version **0.5.0** draws figures directly in the browser using SVG and offline
**Matplotlib glyph outlines**. No Python API or Pyodide runtime is needed.
The surrounding page now uses **native HTML/CSS**, local Nimbus fonts and editable
[`web/presets/papers.json`](web/presets/papers.json). No LaTeX compilation is needed. Page layout and pagination run entirely in the
browser, including figure rendering. Static hosting is sufficient. Figure width and height controls redraw the chart at the chosen physical size.
Template typography stays fixed. Automatic checks now include surrounding-paper
fit and typography; warning cards locate issues and link to the relevant controls.
The data-aware handoff includes separate browser checks and a validated
[skill importer](skills/scientific-figures/references/browser-handoff.md).
Only the first reference page is rendered;
excess example prose is omitted. Interface styling can be adjusted in
`web/src/design-overrides.css`.
The page is a proportional reference; browser line breaks and float placement
are not promised to match LaTeX. See [`web/README.md`](web/README.md) for the design
and alternatives considered. Earlier exact-page measurements under
`tests/web/calibration/` describe the retired compiled-page preview, not this workflow.

| Venue | Narrow (default) | Wide |
| --- | --- | --- |
| ICLR 2026 | half the text width, 69.85 mm | the full text width, 139.70 mm |
| NeurIPS 2026 | half the text width, 69.85 mm | the full text width, 139.70 mm |
| ICML 2026 | one column, 82.55 mm | both columns via `figure*`, 171.45 mm |

LaTeX remains optional for the separate conference fixture tools. Nothing is
deployed — the tree under `web/` is a static site ready to be served, and
publishing it is the repository owner's call.
A ready-to-use [GitHub Pages workflow](.github/workflows/pages.yml) publishes
`web/` from `main`; enable **Settings → Pages → Source → GitHub Actions**. See
[deployment setup](web/README.md#github-pages-deployment) for the one-time steps.

## Tests

For a reproducible development environment, use uv with the committed
`.python-version` (Python 3.12) and `uv.lock`:

```sh
uv sync --locked --all-extras
uv run --all-extras python -m pytest
```

If uv is installed only inside this project's virtual environment, use
`.venv/bin/uv` in place of `uv` and add `--inexact` to `sync` to retain it.
The web extra installs the Python browser tooling; Playwright browser binaries,
the Pyodide runtime and the LaTeX/Poppler toolchain are separate downloads.

```sh
.venv/bin/pip install pytest pypdf
.venv/bin/python -m pytest
```

`tests/` is both the test suite and the worked reference:

```
tests/data/                        prefab specs — the input format, by example
tests/render_gallery.py            renders them all; regenerates the proof sheet
tests/output/                      the committed result: five files per case, plus index.md
tests/render_conference_context.py builds the in-page proof sheet
tests/output/conference-context/   its committed result: one body page per venue and case
tests/fixtures/                    the venues' style files and the body-text excerpt
tests/conference_context/wrappers/ one test document per venue
tests/web/                         the browser tool's tests and its committed evidence
tests/test_*.py                    the behaviour tests
```

The suite checks observable behaviour: every prefab case produces every
deliverable, data order and point counts survive the drawing, the PDF page and PNG
pixel sizes match the profile, editing the profile changes both templates, bad
input fails with a message naming the field, missing glyphs and unavailable fonts
are reported rather than hidden, the skill directory still runs after being copied
elsewhere, and the committed proof sheet matches the current profile and data.

The conference-context tests add: the venue style files are byte-for-byte the
ones the manifest recorded, no wrapper touches the page geometry, every citation
in the body excerpt has a real bibliography entry, the target width follows each
venue's own column rule, a figure rendered to that width lands at scale 1, a
figure that is *not* is reported as shrunk rather than unchanged, each committed
page is one body page and not a title page, and every input that would make a
committed page stale is fingerprinted. The ones that actually compile LaTeX are
marked `conference_context` and skipped when the toolchain is absent.

The browser tests in `tests/web/` add: every published copy of the repository's
Python still matches its source, the runtime is pinned by digest, the packaged
fonts have the same advance widths as the fonts in the compiled PDFs, **every
control in the panel actually changes the drawing** (a knob bound to a field the
renderer ignores is the failure this guards against), a superseded render never
replaces a newer one, an invalid spec comes back as a sentence, export is refused
until the current configuration has been drawn, a clipboard refusal shows the text
instead, and forty renders do not grow the worker's heap. They skip with a message
naming the missing command when the runtime, the fonts or Playwright are absent.

## Contact

Questions and bug reports are welcome as issues, or at cbhua@kaist.ac.kr.
