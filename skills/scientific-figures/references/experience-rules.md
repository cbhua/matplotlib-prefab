# General figure constraints and reference policy

Use this catalog when applying or extending the skill's rules. Descriptive
constraints apply across templates; conference files resolve them into concrete
physical values. The initial reference is
[conference-presets/iclr2026-first.json](conference-presets/iclr2026-first.json).
Read that file for numbers; do not copy ICLR point sizes to a different template
without checking its body size and insertion geometry.

## Rule catalog

`error` means invalid/unfaithful or impossible output; `warning` means a
recommendation or heuristic requiring review; `info` is descriptive evidence.
These categories express the decision, not a claim that every renderer
implements a detector. Coverage is in [rendering-workflow.md](rendering-workflow.md).

| Rule | Intended decision | Evidence and safe response |
| --- | --- | --- |
| `data-integrity` | Error for silent data/label/order changes, invalid inputs, hidden observations or misleading bar baselines | Compare input with drawn values/counts/order; retain zero categories. Fix layout or obtain missing data, never fabricate or delete it. |
| `physical-size` | Error for an export violating its requested physical canvas; warn/review unintended insertion scaling | Measure exported PDF and actual document placement. Re-render at the final slot width instead of scaling the whole image. |
| `paper-relative-typography` | Warn when a present role falls outside the selected reference | Compare final point sizes with template body text and role bounds. Axis labels should visually match prose at a slightly smaller nominal size; ticks remain readable and smaller than labels; legends remain comparable to or smaller than prose. |
| `axis-label-consistency` | Warn when X/Y label sizes differ | Compare resolved per-axis sizes only in panels with both titles. Use a numerical tolerance, not an aesthetic score. |
| `text-legibility` | Warn for text collisions/clipping; error for missing glyphs | Inspect actual rotated text geometry and final export. Increase space, adjust tick placement/rotation or revise layout before shrinking below readable bounds. |
| `legend-data-clearance` | Warn when the legend's reading rectangle intersects actual data ink | Include data strokes/markers beneath an opaque or transparent legend; exclude gridlines and legend handles. Reposition or reserve outside space. Do not hide the offending curve. |
| `outside-legend-layout` | Error if the selected arrangement cannot fit | Honor inside/outside and an explicit top/bottom/left/right side. Reserve space within the full canvas, preserving physical type/strokes. Deduplicate only matching name AND drawn style; distinguish same-name/different-style entries by source panel. |
| `print-strokes` | Warn for strokes below the selected print floor; review excessive visual weight | Start from the reference widths; assess contrast, density and print process. There is no adopted universal upper limit. |
| `series-distinguishability` | Error for exhausted indistinguishable renderer styles; review color/print perception | Check drawn color, dash and marker assignments. Reinforce important series differences with channels beyond hue. |
| `wrapped-figure-width` | Warn for narrow caption space or squeezed adjacent prose | Compare figure width with available body text width excluding margins, and subtract the wrap gap before measuring remaining prose. Apply only when text wraps. |
| `article-fit` | Warn for figure/caption spill into margins/footer or overlap with prose | Check the whole float and actual text fragments. Recheck the real document when placement verification is requested. A standalone size check cannot prove this. |
| `plot-area` | Warn when labels/legend squeeze the usable plot region | Measure the plot relative to its allocated panel, not the entire multi-panel canvas. Enlarge/rearrange within the allowed paper slot. |
| `marker-overdraw` | Warn for substantial repeated marker coverage, not every crossing | Combine visible-mark count, redundant area and fraction of overlapping marks. Repeated coordinates may be a result; preserve data and adjust marker size or layout. |
| `recoverable-space` | Warn for a large contiguous unused region in an already large plot | Reserve breathing room around data/legend first; require physical size and fractional criteria together. Consider reducing dimensions without clipping or changing values/baselines. |
| `ink-context` | Info only | Record figure/body foreground coverage, mean contrast and edge transitions with method/resolution. Prose ink is not an optimal target or a measure of scientific information. |
| `bar-space-distribution` | Info only | Record category/zero counts, space per category, bar fill, horizontal gaps, top space and band-wise occupancy. Few bars or low fill alone do not justify a warning. |
| `visual-review` | Explicitly unverified until someone opens the output | Inspect type, legend, encodings, spacing and scientific context. A clean report is not publication certification. |

## Resolving typography

Load body size and role ranges from the selected conference reference. Axis
labels use a body-relative target and tolerance; keep X/Y equal unless the
user deliberately chooses otherwise. Check styles after optional per-axis
fallbacks have resolved, and verify they reached the actual text artists.

Ticks use the intersection of the calibrated print-size range and the interval
around the corresponding axis-label-relative target. Bounds are inclusive. If
an invalid label size makes these intervals disjoint, report/defer that relative
constraint, retain the calibrated print range and fix the axis label first.
Never recommend an impossible interval. An absent title is exempt from title
size, X/Y consistency and that axis-relative tick relationship; visible ticks
still need the calibrated print-size check. A missing legend has no legend-size
warning. Group shared-style warnings by role with affected panel indices.

The ICLR reference expresses the owner's current visual calibration beside its
body text. It is not a font-family rule: nominal points only approximate perceived
size, which also depends on x-height, family and weight. Serif/sans-serif design
preferences were deliberately deferred. The generic profile's bundled font is
an operational fallback for portability.

## Legends and chart labels

An inside location such as `best` is a placement attempt, not proof of clearance.
Protect the entire legend reading area, including a frameless one. The browser
samples actual stroke/marker shapes with dash gaps and plot clipping respected;
finite raster sampling still needs visual confirmation on the final renderer.
Python does not execute that browser detector.

Outside mode uses one shared framed legend within the canvas. The bundled
renderer supports line/scatter series, including a single series when an outside
legend was explicitly requested. Ungrouped bars name categories on their axis
and need no series legend. Preserve explicit side choices. Older handoffs with
an outside legend but no side retain their legacy automatic placement; new
configurations specify a side.

For bars, start with the reference's modest category-label rotation and inspect
actual label clearance. Use oriented text bounds so parallel rotated labels are
not falsely called collisions just because their axis-aligned boxes overlap.
Do not shorten/drop category names without authorization or change the zero
baseline to occupy more space.

## Space and density

[visual-density.md](visual-density.md) documents research, measurement methods
and limitations. The initial preset records the current diagnostic thresholds
for interpretation; they are shared project heuristics, not conference rules.
The browser computes them; the Python preset path reports them as not checked.

Keep ink coverage, marker overdraw and recoverable space distinct. For bars,
report category count and nonzero count separately, physical width/area per
category, filled and occupied fractions, maximum horizontal gap, top space and
horizontal/vertical band loads. Zero categories remain present. Scientific
information depends on the comparison, uncertainty and task, not bar area.

A missing/failed measurement is `not_checked` with a reason, never zero or pass.
Browser evidence uses physical coordinates and excludes UI zoom, preview grids
and page decoration. Re-rendering in another engine invalidates an assumption
of pixel-identical collision/density results.

## Provenance and extension

Keep three origins distinct: measured template geometry, project-owner style
preferences, and engineering heuristics. An explicit publisher requirement can
override a local recommendation when actually applicable; do not promote it to
a universal constraint. In particular, researched publisher stroke minima do
not establish an optimal data-line width or an upper limit.

Previously reviewed publisher sources (2026-10-16):

- [Springer, Mathematische Zeitschrift](https://link.springer.com/journal/209/submission-guidelines): production line-art lower bound; not an optimal chart stroke size.
- [PLOS ONE figures](https://journals.plos.org/plosone/s/figures): its SigmaPlot export instructions have software-specific stroke/type recommendations; retain that scope.
- [IEEE conference graphics](https://conferences.ieeeauthorcenter.ieee.org/write-your-paper/improve-your-graphics/): legibility, consistency and distinguishable encodings; no adopted universal heavy-line cutoff.

To add a rule, give it a stable identifier, applicability, severity, evidence,
provenance, limitations and safe remediation. Put its numerical reference values
in the applicable preset; keep descriptive guidance here. Add a boundary or real
render regression for an implemented evaluator. Do not turn an uncalibrated
metric into a warning without reviewed examples.

Repository integration: `web/src/experience-rules.js` is the existing browser
registry (revision 3), with density/occlusion parameters in focused modules.
Browser handoffs retain that registry and measured evidence. The skill packages
its own portable ICLR reference; cross-layer tests detect drift against the
current browser calibration. Changing a rule requires updating both consumers
or documenting why their scopes differ, not editing generated web assets.
