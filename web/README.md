# The browser style lab

A static page that shows a single-panel matplotlib figure at its printed size,
inside a page of a real conference template, and lets you change the type sizes,
weights, line widths, tick counts and bar settings with the figure redrawing as
you go. Then it hands you a configuration another agent can reproduce.

Nothing about it is a mock-up:

* the figure is drawn by **this repository's `figure_core.py` and templates**,
  running in the browser under Pyodide — not by a JavaScript chart library
  imitating them;
* the paper page is **generated from a compiled LaTeX page** of the venue's own
  style file, down to each line's baseline and the face each run is set in;
* the figure slot is the width **the template's own arithmetic** gives a figure
  in that mode.

It also runs `render.py`'s own live checks on every draw — the same functions
with the same thresholds — so pushing the type up until the tick labels collide
gets you a warning rather than a crowded figure and silence. The slot never grows
to accommodate a setting; a figure that does not fit is reported as not fitting.

The evidence for all three, with numbers, is in
[`../tests/web/calibration/`](../tests/web/calibration/).

## Run it

```sh
python scripts/fetch_pyodide.py        # ~24 MiB, once; pinned by web/pyodide.lock.json
python scripts/build_fonts.py          # packages the venue body faces as WOFF2
python scripts/build_web_assets.py     # copies this repo's Python, profile and specs
python web/serve.py                    # http://127.0.0.1:8765/index.html
```

`file://` will not work: the tool loads a Web Worker and a WebAssembly module,
and browsers refuse both from a file URL. Any static HTTP server will do;
`web/serve.py` exists so the repository has a command that needs nothing
installed.

To rebuild everything including the calibrated pages (needs LaTeX and a browser):

```sh
python scripts/build_and_verify_web.py
```

## What it promises, and what it does not

**It promises** that the same spec and profile drawn here and drawn by
`render.py` in an interpreter pinned to the same matplotlib produce a
byte-identical SVG, and that this page and the same page compiled by the venue's
LaTeX agree to better than 0.03 mm per text run. Both are measured, per release,
in `tests/web/calibration/`.

**It does not promise:**

* that the same style over *different data* gives the same figure — the legend
  position, the tick values and the layout all move with the data;
* that a different matplotlib draws the same thing — the version is pinned and
  named in every export;
* that *your* paper compiles, that your float lands where you want it, or that
  your macros are compatible. This is a fixture page, not your document;
* that a successful render is a visual review. Someone still has to look.

The style values it starts from are this repository's **provisional** choices,
not a venue requirement.

## How it is put together

```
web/
  index.html                the shell: tabs, toolbar, preview, panel
  pyodide.lock.json         every runtime file, pinned by sha256
  serve.py                  local preview server (correct MIME for .wasm/.mjs)
  src/
    app.js                  orchestration; owns the "never show a stale figure" rule
    paper-page.js           draws page.json onto the sheet
    paper-page.css          the sheet's geometry — nothing decorative
    controls.js             every control and the profile field it writes
    export-config.js        the hand-off text and the machine-readable bundle
    render-worker.js        Pyodide in a Web Worker, one job at a time
    python/worker_render.py the worker's thin Python side
    styles.css              the tool's own chrome
  public/generated/         built; not hand-edited
    assets-manifest.json    what was copied from where, with digests
    python/skill/           figure_core.py, inspect_figure.py and the templates, byte for byte
    profiles/, specs/       the repository's profile and example specs
    conferences/<venue>/<mode>/page.json   the calibrated page manifests
    fonts/                  the venue body faces, WOFF2, plus their licence
    pyodide/                the fetched runtime (gitignored)
```

Everything under `public/generated/` is produced by a script and checked by
`tests/web/test_web_assets.py`, which fails if a copy no longer matches its
source. Editing a copy instead of its source makes the site and the command line
disagree, which is the one failure this whole design exists to prevent.

### Why the page's text is SVG

A run has to sit on a measured baseline. CSS gives no way to say "put this
text's baseline here" — the offset from a positioned box's top to its baseline
depends on the strut, the line-height and the font's ascent metrics, so an HTML
span would have to be nudged by a number derived from the font rather than from
the page. `<text y=…>` *is* the baseline, by specification. The text is still
real text: selectable, copyable, in reading order, set in the actual font.

### Fonts

All three templates set their body in URW Nimbus Roman No9 L (what the `times`
package loads) with Nimbus Mono for `\texttt`. Those faces are packaged as WOFF2
from the system `urw-base35` fonts, and `scripts/build_fonts.py` compares every
advance width against the `/Widths` array of the font actually embedded in each
compiled venue PDF. At the last run: 79 glyphs per face, zero mismatches.

The inline maths is Computer Modern, which has no equivalent web font. Rather
than substituting a different italic and calling it maths, those glyphs are
emitted as SVG paths lifted from the Type 1 program embedded in the baseline PDF
itself — same font, same page, recorded provenance. There are seven such glyphs
across the pages.

The Nimbus faces are URW's, under the GNU AGPL v3 with the URW font exception,
redistributed with their licence in `public/generated/fonts/`. A repository owner
publishing this site should confirm that position for their own distribution.

## Deploying

The build produces relative paths only, so the tree under `web/` can be served
from a subpath (a GitHub Pages project site, say). Nothing has been deployed by
this work and no publishing workflow was added.

Publishing it means serving `web/` including `public/generated/pyodide/`, which
is fetched rather than committed — about 24 MiB. The first visit downloads that;
there is no offline caching and none is claimed. All computation is in the
visitor's browser: no user data is sent anywhere and no server-side rendering is
involved.
