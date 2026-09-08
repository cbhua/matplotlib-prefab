# Checking a figure in a real article page

A `figure.pdf` proves the canvas is 85 mm wide. It proves nothing about whether
the figure is readable, because a reader never sees it at 85 mm on a white
background — they see it at whatever width the template gives a figure, wrapped
in 10 pt body text, under a caption set in the venue's own style.

Those are different sizes. ICLR 2026 and NeurIPS 2026 set a 5.5 in text block, so
half of it is 69.85 mm. ICML 2026 is two-column: 6.75 in of text minus 0.25 in of
column separation leaves 82.55 mm per column. Drop an 85 mm figure into the ICLR
slot and everything in it shrinks by a factor of 0.82 — 9 pt axis labels print at
7.4 pt, 1.2 pt data lines at 0.99 pt. Nothing in `report.json` would tell you
that, because `report.json` only ever looked at the figure on its own.

This is the check that closes that gap.

## What it does

```sh
python tests/render_conference_context.py --all
python tests/render_conference_context.py --venue iclr2026 --case line-multi
```

For one venue and one figure it compiles the venue's own LaTeX style around an
excerpt of real running prose, drops the figure in as an ordinary centred float,
finds the body page it landed on, and keeps three things:

| File | What it is |
| --- | --- |
| `page.pdf` | That one page, whole and uncropped — margins, running head, folio, caption, prose |
| `page.png` | A 200 DPI raster of it |
| `context-report.json` | Every measurement, with its unit and where it came from |

The full multi-page PDF, the `.aux`, the `.log`, the `.bbl` and the derived
profile live in a temporary build directory that is deleted on success. On
failure the build directory is copied to `.tmp/conference-context-failures/` and
the path is printed.

## How the width is decided

Not by reading a number out of a style file. Two compiles:

1. **Probe.** Compile the wrapper with a placeholder box where the figure goes.
   `measure.tex` writes out `\textwidth`, `\columnwidth`, the `\linewidth` the
   float actually sees, the body font size and the caption font size — measured
   by TeX, in the document, at the insertion point.
2. **Place.** Multiply that `\linewidth` by the venue's factor, copy the profile
   with `canvas.width_mm` set to the result and **nothing else changed**, render
   through the ordinary `render.py`, and compile again with the real figure.

| Venue | Layout | Figure gets |
| --- | --- | --- |
| ICLR 2026 | one column | 0.5 × `\linewidth` (= half the text width) |
| NeurIPS 2026 | one column | 0.5 × `\linewidth` |
| ICML 2026 | two columns | 1.0 × `\linewidth` (= one whole column) |

ICML is the one people get wrong. Half the *text* width there would be 85.7 mm,
which is wider than the column the figure has to fit in. The column separation is
already taken out of `\columnwidth`, so a two-column venue gets a whole
`\linewidth`, not half of one.

Because the derived profile keeps every font size and line width, the figure
arrives on the page at **scale 1**: a 9 pt label is 9 pt on the page. That is the
point of re-rendering rather than scaling.

## What "measured" means here

The report does not trust the `\includegraphics[width=…]` argument it wrote.
That argument is what was *asked for*; the check is what the page actually
*draws*. The evaluator walks the compiled page's content stream, tracks the
graphics state through `q`/`cm`/`Q`, finds the form XObject carrying the figure
and multiplies its `/BBox` through the drawing transform. `geometry.placed_width_mm`
is that number.

Units are kept apart on purpose, because confusing them is a 0.4 % error and the
width tolerance is 0.5 %:

* **TeX points** — 72.27 per inch. Everything `measure.tex` writes; keys end `_tex_pt`.
* **PDF points** — 72 per inch. Everything read out of a PDF; keys end `_pdf_pt`.
* **mm** — the physical size, and what the summary line prints.

## Reading the report

`context-report.json` has one entry per check, each `pass`, `warn`, `fail` or
`not_checked`, plus these blocks:

| Block | Carries |
| --- | --- |
| `template` | text width, column width, the `\linewidth` at the float, body and caption pt |
| `geometry` | target, source and drawn widths, the drawing matrix, `scale` |
| `type_sizes` | the figure's source pt, the effective pt after scaling, body and caption pt to compare against |
| `page` | PDF page index (zero-based), printed folio, total pages, page size |
| `fixtures` | digests of the template, wrapper, body text and bibliography used |
| `environment` | LaTeX and poppler versions, rasterisation DPI |

Checks worth knowing:

| Check | Means |
| --- | --- |
| `placed_width_matches_target` | The drawn width agrees with the width rule, within 0.5 % |
| `effective_type_size` | `pass` at scale 1; `warn` with the reduced sizes spelled out when the figure was shrunk; `not_checked` when the figure came without a profile, so the source sizes are unknown |
| `page_is_body_page` | The page is not the title page and carries real prose |
| `page_index_consistent` | TeX's folio and the PDF page index agree — the extracted page is the one the report describes |
| `latex_references_resolve` | No undefined citation or cross-reference |
| `visual_review` | Always `not_checked`. No script closes it |

`effective_type_size` deliberately sets **no threshold**. It reports that a 9 pt
label prints at 7.4 pt next to 10 pt body text, and leaves the judgement to you.
"Figure text must match body text" is not a rule this project has established,
and inventing one here would dress a guess up as a check.

## Then look at the page

The PNG is the point. Open it and read the figure the way a reviewer would, with
the prose beside it for scale:

* Are the tick labels still readable against the body text next to them?
* Does the legend still sit clear of the data at this width?
* Are the series separable by dash and marker, not just colour, at this size?
* Is the caption doing work the figure should be doing?
* Is there dead space that a narrower figure would not have?

**A 200 DPI preview scaled to your screen is not the printed size.** The physical
size is the one in `geometry`, measured from the PDF. To see the real thing, open
`page.pdf` at 100 %.

If the figure needs fixing, fix it the usual way — a profile copy, at most two
rounds — and re-run the context evaluation, because changing the figure changes
the page.

## Requirements, and what to say when they are missing

Needs `latexmk`, `pdflatex`, `bibtex` and `pdftoppm`. On Debian/Ubuntu:

```sh
sudo apt install texlive-latex-recommended texlive-fonts-recommended \
                 texlive-latex-extra latexmk poppler-utils
```

`python tests/render_conference_context.py --check-dependencies` says whether
they are there.

None of this is needed to render a figure. `render.py` uses matplotlib mathtext
and no LaTeX at all.

When the toolchain or the fixtures are missing, the generator exits non-zero
rather than skipping. Report it the same way: the figure was produced, the
article-context check **did not run**, and therefore nothing is known about how
the figure looks on the page. An evaluation that did not happen is not one that
passed.

## Using it from a copied skill

`evaluate_context.py` holds no repository paths. Give it the three fixture
directories:

```sh
python <skill>/scripts/evaluate_context.py \
    --venue iclr2026 --case my-figure \
    --spec my-spec.json \
    --output-dir out/ \
    --conferences-dir <fixtures>/conferences \
    --article-dir <fixtures>/article-context \
    --wrappers-dir <fixtures>/wrappers
```

or `--fixtures-root <dir>` if all three sit under one directory as
`conferences/`, `article-context/` and `wrappers/`. Without them there is no
template to measure, and the script says so instead of guessing a width.

## Width modes

Each venue offers two, declared in `tests/fixtures/conferences/manifest.json` and
selected with `--layout`:

| Venue | `narrow` (default) | `wide` |
| --- | --- | --- |
| ICLR 2026 | half the text width, 69.85 mm | the full text width, 139.70 mm |
| NeurIPS 2026 | half the text width, 69.85 mm | the full text width, 139.70 mm |
| ICML 2026 | one column, 82.55 mm | both columns, 171.45 mm |

The factor is applied to the `\linewidth` measured *inside the float that mode
uses*, so an ordinary `figure` sees `\columnwidth` in a two-column document and a
`figure*` sees `\textwidth`. That is why ICML's narrow mode is a whole column
rather than half the text width: the column separation has already been taken out.

`wide` on ICLR and NeurIPS is a full-text-width figure in a one-column template —
**not** a second column. Those templates have one. Only ICML's `wide` uses a real
`figure*`, which is the template's own cross-column mechanism; LaTeX defers such a
float to the top of a later page, so which page it lands on is the template's
decision, not the evaluator's.

A wider mode does not change any type size. A figure that spans the text block is
a wider figure, not a magnified one.

`narrow` is the default everywhere, and
`tests/render_conference_context.py` still runs the narrow matrix only. The wide
baselines live with the browser tool, under `tests/web/calibration/baselines/`.

## Three ways to look at a figure in context, and what each one proves

| | What it is | What it proves |
| --- | --- | --- |
| The browser style lab (`web/`) | A calibrated fixture page in the browser, redrawn live | The figure at its printed size next to real body type, without needing LaTeX. Its pages match the compiled ones to better than 0.03 mm per text run — see `tests/web/calibration/`. |
| This evaluation | A real LaTeX compile of a real template | That the venue's own style, at the width its own arithmetic gives, produces this page. The one to run when a template or the tool changes, and when a figure must be integrated for real. |
| Your own paper | Your document | Only this proves your paper compiles, your float lands where you want it and your macros behave. Neither of the other two says anything about it. |

The browser preview is the day-to-day one; this evaluation is the baseline that
makes the browser preview worth trusting. Neither closes `visual_review`.

## Scope and honesty

* One figure per page, single-panel. `narrow` and ICML's `wide` place it in an
  ordinary centred `figure`; ICML's `wide` uses the template's own `figure*`.
  There are still no side-by-side pairs, no `wrapfigure` and no multi-panel
  figures — that matches what this skill can draw. A cross-column *width* is a
  width, not a new kind of figure.
* The compiled documents are **typesetting fixtures**. Their titles, authors and
  abstracts say so on the page. Camera-ready mode is used because that is the
  layout a figure is finally judged in — not as a claim that anything was
  accepted anywhere.
* The body prose is an excerpt from a published article, reproduced only as
  typographic context and credited in
  `tests/fixtures/article-context/provenance.md`. The figure in it is synthetic
  evaluation data, and the caption on the page says so.
* The default width rule and the style numbers behind these pages are still the
  project's *provisional* choices. Never present them as a venue requirement.
