---
name: scientific-figures
description: Generate and review scientific paper figures with general rules for physical sizing, readable typography, data integrity, legends and spatial layout. Includes separate conference reference presets and a reproducible Matplotlib renderer for line, bar, scatter and rectangular panel grids. Use for paper figures or browser figure-configuration handoffs.
---

# Scientific figures

Produce a faithful figure that remains readable at its final size in the paper.
Keep **general constraints** separate from **conference reference values**.
Recommendations guide the agent's decisions; a clean automated report does not
certify scientific correctness or publication readiness.

## Choose the reference context

Use the user's template, insertion width and explicit style choices first. If
only a conference is named, load its matching reference; do not assume another
year or venue is equivalent. Ask for missing context only when it changes the
result. For an unspecified standalone figure, use the generic profile and report
that no paper context was verified.

The first packaged conference reference is
[ICLR 2026, first/default template](references/conference-presets/iclr2026-first.json):
one panel, narrow figure, text wrapping beside it. Its file contains paper/body
geometry, calibrated type ranges, stroke defaults, placement constraints and
diagnostic parameters. Template measurements and owner preferences have separate
provenance. Figure recommendations are **not official ICLR requirements**.

For a browser handoff, read [browser-handoff.md](references/browser-handoff.md).
Preserve its actual data, canvas size, placement and selected styles instead of
resetting them to the conference defaults. Browser checks are evidence about
that browser render; repeat applicable checks on the exported figure.

## General constraints

- **Preserve the scientific content.** Keep values, category/series order, units
  and labels faithful to the supplied data. Do not silently sort, drop, round,
  smooth, resample or aggregate observations to fix a visual problem. Distinguish
  synthetic demonstration data from research results. Bar comparisons retain a
  zero baseline and zero-valued categories.
- **Design at the final physical size.** Measure the available text/column
  width, including any space reserved for a shared legend. Render for that slot
  rather than shrinking an oversized export afterward. Point sizes refer to the
  inserted figure, not browser zoom or PNG resolution. Recheck after resizing.
- **Relate type to the surrounding prose.** Aim for axis labels around 90% of
  body-text size, with the selected reference's tolerance. Keep X/Y labels the
  same size. Ticks remain readable and smaller than axis labels; legends stay
  comparable to or smaller than prose. Use the calibrated tick range together with its
  axis-relative constraint; repair an invalid axis size before resolving a
  conflicting range. Check only text roles actually present.
- **Keep text readable and unobstructed.** No accidental clipping, collisions,
  missing glyphs or unreadable category labels. For bars, modest rotation is a
  starting point; inspect actual labels after layout. Choose fonts suitable for
  the user's document; this skill imposes no serif/sans-serif style policy.
- **Protect the legend's reading area.** A legend must not cover curves or
  markers, even if its frame/background is transparent. Try available clear
  space or a separate legend before reducing type below the readable range.
  Support inside or outside placement; an outside legend occupies a reserved
  area on the chosen top/bottom/left/right side of the same canvas. Honor the
  selected side, preserve distinguishable entries, and report an impossible fit.
- **Keep strokes and encodings legible.** Use the reference's print-oriented
  starting widths and inspect the final output for disappearing strokes or
  merged marks. No universal upper line-width cutoff has been established here.
  Multiple series need distinguishable encodings beyond hue alone when needed;
  never silently recycle indistinguishable styles.
- **Fit the article, including its caption.** In text-wrap layouts, leave useful
  width for both caption and prose; a figure roughly one third to two thirds of
  the body text width is the current project recommendation. Use body width
  excluding margins as the denominator. This rule does not constrain ordinary
  non-wrapped/full-width floats. Keep the figure/caption clear of body text and
  footer; verify actual insertion scale when article placement is in scope.
- **Review crowding and empty space separately.** Check real overlaps, marker
  overdraw, plot area squeezed by decorations and large recoverable blank
  regions. Compare figure ink with prose only as context. Pixel coverage, bar
  count and filled area do not measure scientific information or determine
  whether a figure is good. Never add decoration or alter data to improve them.

For the full rule catalog, scope and remediation, read
[experience-rules.md](references/experience-rules.md). For a crowded/sparse figure
or browser density evidence, also read [visual-density.md](references/visual-density.md).

## Generate and verify

The bundled renderer handles numeric line/scatter series, vertical ungrouped
bars, and rectangular grids of these. Read [input-schema.md](references/input-schema.md)
before writing a spec; it rejects unknown fields. Other chart types can use these
general constraints with an appropriate renderer, but this bundled CLI does not
implement them. Do not disguise an unsupported scientific encoding as a supported
one or claim that the bundled checks ran on another renderer's output.

Requires Python, Matplotlib and NumPy; drawing needs no LaTeX. Paths below are
relative to this skill directory; invoke its scripts by their actual location.
For a self-contained smoke example (synthetic data only):

```sh
python scripts/render.py \
  --preset iclr2026-first \
  --spec assets/examples/line.json \
  --output-dir <output-directory>
```

Replace the example with the user's spec. `--preset` resolves the separate
reference into a render profile and adds reference checks. Use `--profile` as
well to retain an edited full profile while checking against that reference.
Use `--text-wrap off` for non-wrapped placement. Without `--preset`, the generic
profile and existing rendering behavior remain available.

Deliver `figure.pdf`, `figure.png`, `spec.json`, `profile.resolved.json` and
`report.json`. The report records applied settings, checks, the reference
snapshot and a reproduce command. Read warnings and failures, then **open the
actual PNG/PDF** to review legend clearance, type, clipping and spacing at the
target size. Fix layout/style within the task's scope and re-render; preserve
the data and explain unresolved tradeoffs. See
[rendering-workflow.md](references/rendering-workflow.md) for report interpretation
and renderer mechanics.

Python checks physical outputs, artist styles and data integrity; selecting a
preset also checks paper-relative typography, X/Y consistency, reference width
and stroke visibility. **It does not run the browser's legend-occlusion or
density measurements, or prove article placement.** These remain explicitly
`not_checked`. The automatic `visual_review` entry also stays `not_checked`;
report any review you actually performed separately, without rewriting it as an
automated pass.

When the user asks for verification in the real paper, use
[article-context-evaluation.md](references/article-context-evaluation.md) with
their document or explicitly supplied fixtures. Compilation requires LaTeX and
Poppler; the skill does not bundle conference templates. If unavailable, deliver
the figure and state that article placement was not verified.

Hand over the artifacts, target physical size, applied reference, unresolved
issues, actual review coverage and reproduction command. Do not claim a venue
mandates the project's chosen values or that unperformed checks passed.
