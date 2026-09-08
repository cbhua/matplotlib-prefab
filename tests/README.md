# tests

Two jobs in one directory: the behaviour tests, and the worked reference for
using the skill.

```
data/                        prefab specs — the input format, by example
render_gallery.py            renders every spec with the current profile
output/                      the committed result: five files per case, plus index.md
output/conference-context/   the same figures set into real ICLR/NeurIPS/ICML pages
render_conference_context.py builds those pages
fixtures/conferences/        the venues' own style files, plus a manifest of where they came from
fixtures/article-context/    the body-text excerpt, its bibliography, and its provenance
conference_context/wrappers/ one test document per venue, plus the TeX measurement harness
test_*.py                    the behaviour tests
helpers.py                   shared fixtures; conftest.py puts the skill on sys.path
```

## Adjusting the preset style

Every style value lives in one file:
`../skills/scientific-figures/references/profiles/single-column.json`. To change
one and see what it does:

```sh
python tests/render_gallery.py     # from the repository root
open tests/output/index.md
```

`index.md` prints the values in force directly above the pictures they produced.
The six cases exist to make each knob visible:

| Case | What it lets you judge |
| --- | --- |
| `line-single` | line width, marker size and spacing, tick and label sizes, no-legend rule |
| `line-multi` | the first three palette colours, bound marker shapes, legend size and placement |
| `line-many` | eight series: colours run out and the dash pattern takes over — are 7 and 8 still separable from 1 and 2? |
| `line-mathtext` | mathtext: italic variables, upright units, no LaTeX involved |
| `bar-positive` | bars sitting on the baseline, one colour per series, bar width, category spacing |
| `bar-signed` | the zero line, padding either side of zero, a zero-valued category |

`--case <name>` renders one of them; `--profile <path>` renders the whole sheet
with a profile copy, without touching the committed one.

After changing the profile, regenerate the *page* sheet too — the figures on
their own and the figures on a page are different questions:

```sh
python tests/render_conference_context.py --all
open tests/output/conference-context/index.md
```

## Figures in real conference pages

`tests/output/conference-context/` is the proof sheet that answers "what does
this look like at the size a reader gets it?". Seven pages: three venues x two
cases rendered at the template's own width, plus one regression case that drops
the committed 85 mm figure into ICLR's half-width slot without redrawing it, so
the reports have to show a real 0.82 scale factor rather than claim the labels
are still 9 pt.

| Venue | Layout | Figure width |
| --- | --- | --- |
| ICLR 2026 | one column, `\iclrfinalcopy` | half the text width |
| NeurIPS 2026 | one column, `[main, final]` | half the text width |
| ICML 2026 | two columns, `[accepted]` | one whole column |

Each case keeps three files — `page.pdf` (one whole body page, uncropped),
`page.png` and `context-report.json`. The multi-page PDF, the aux files and the
derived profile stay in a temporary build directory; on failure it is copied to
`.tmp/conference-context-failures/` and the path is printed.

Widths are never hard-coded. A first compile measures `\textwidth`,
`\columnwidth` and the `\linewidth` the float actually sees; the figure is then
re-rendered at that width and placed. The width in the report is read back out of
the compiled page's own drawing transform, not out of the `\includegraphics`
argument. `skills/scientific-figures/references/article-context-evaluation.md`
explains the whole thing.

The venue style files are byte-for-byte what the archives shipped —
`tests/fixtures/conferences/manifest.json` records the source archive, its
SHA256, and a digest per file, and a test fails if any of them changes. Nothing
about the page geometry may be adjusted to flatter a figure. The prose is an
excerpt from a published article used purely as typographic context and credited
in `tests/fixtures/article-context/provenance.md`; the figures are synthetic. The
compiled documents say on their own title pages that they are fixtures, not
submissions.

### Observations from the visual review

Recorded 2026-09-08, from actually looking at all seven pages. These are human
judgements, not check results — no script produced them and none will close them.

1. **`bar-signed`'s category labels collide at half width.** Five labels
   (`Baseline`, `Dropout`, `Mixup`, `Label smth.`, `EMA`) fit at ICML's 82.55 mm
   column and run together at ICLR/NeurIPS's 69.85 mm: the page reads
   "BaselineDropout MixupLabel smth.EMA". `render.py` does flag it
   (`tick_label_overlap`, `text_within_canvas`) at that width, and the context
   report now carries those warnings up under `figure_render_checks` — but the
   figure at 85 mm on its own gives no hint of it. This is the finding the whole
   evaluation exists to produce. Unresolved: rotating the labels, shortening
   them, or accepting that five categories need a full-width figure is a profile
   decision for the repository owner.
2. **The figure's type reads larger than the body type**, on all three venues, at
   scale 1. The figure is set in 9 pt/8 pt DejaVu Sans and the templates set 10 pt
   Times; DejaVu Sans has a far larger x-height, so nominally *smaller* figure
   type looks bigger than the prose beside it. Whether that is wrong is a
   judgement — the automated check deliberately sets no threshold — but it is
   visible on every page and worth deciding about before the profile is
   finalised.
3. Everything else looks right: the figure sits centred in an ordinary float, the
   caption is in each venue's own style (ICLR/NeurIPS 10 pt "Figure 1:", ICML 9 pt
   italic "Figure 1."), the running head, folio, margins and reference list are
   the template's, and the regression page's figure is visibly smaller-set than
   the scale-1 one.

### Requirements

This part needs LaTeX and poppler; the rest of the repository does not.

```sh
sudo apt install texlive-latex-recommended texlive-fonts-recommended \
                 texlive-latex-extra latexmk poppler-utils
python tests/render_conference_context.py --check-dependencies
```

Without them the generator exits non-zero rather than pretending: an evaluation
that did not run is not one that passed.

## Why the output is committed

So the pictures can be reviewed in the repository and in a diff, and so the
preset values are visible without running anything. `test_gallery.py` keeps that
honest: it compares each committed render against the current profile and the
current spec, and fails with `run python tests/render_gallery.py` if they have
drifted apart.

## The browser tool's tests and evidence

`web/` in this directory holds both: the tests that drive the style lab in a real
browser, and the committed measurements they assert on. See
[`web/README.md`](web/README.md) for what each report answers and how to
regenerate it.

The short version: the paper pages the browser shows are generated from compiled
LaTeX pages by `scripts/calibrate_conference_pages.py`, and every claim about how
closely the browser reproduces them — per-run baselines, left edges, widths, the
figure slot, and the whole page compared against a LaTeX page built from the
browser's own export — is a number in `web/calibration/`, not an assertion in
prose. Each report carries a digest of every file that could change it, so it
cannot outlive the code it describes.

```sh
python scripts/build_and_verify_web.py   # regenerate all of it
python -m pytest tests/web -q            # check it
```

## Running the tests

```sh
python -m pytest                        # everything that can run here
python -m pytest -m conference_context   # only the tests that compile LaTeX
python -m pytest -m "not conference_context"
python -m pytest tests/web                # only the browser tool
```

Tests render into pytest's `tmp_path`; only `render_gallery.py` and
`render_conference_context.py` write `output/`. `pypdf` is needed for the
page-size assertions (`pip install pytest pypdf`).

The `conference_context` tests compile the three templates and are skipped when
LaTeX or poppler is missing — a skip that says the check did not run. Everything
else about the conference pages is checked without a compiler: the committed
reports, their measurements, and a per-case digest of every input that would make
them stale (templates, wrappers, body text, spec, profile and the rendering code).
Comparing only the default profile would not be enough, since these pages are
rendered at a derived width.
