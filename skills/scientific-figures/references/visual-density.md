# Visual density, crowding, and wasted space

Use this reference when reviewing an overly busy or empty panel, or interpreting
`checks.visual_density` in a browser handoff. Research reviewed 2026-10-16.

## Decision

Treat visual density as several measurements with distinct meanings. Use direct
geometry to warn about collisions/overdraw and recoverable empty space. Show
figure-to-body ink ratios as descriptive context. Do not force charts to match
prose density, infer scientific information from pixel counts, or assign a
universal aesthetics score.

The rules below are project engineering choices. Published studies support the
choice of phenomena to measure; **they do not validate our numeric thresholds**.
A clean diagnostic is not evidence of readability, task performance or beauty.

## Research and implications

| Approach | Evidence | Decision for this tool |
| --- | --- | --- |
| Feature Congestion, Subband Entropy | Rosenholtz, Li & Nakano (2007) model visual clutter through local feature variability and multiscale image organization, testing image-based measures against visual search. | Valuable research baselines, but not interchangeable with foreground pixel coverage. We do not claim to implement either model. |
| Task and encoding dependent complexity | Chu et al. (IEEE VIS 2025) study 1,800 visualization images and 349 participants; useful predictors differ across stimulus types. | A single pixel ratio cannot be promoted into a general chart-quality cutoff. A future learned model needs independent validation on our chart tasks. |
| Overdraw | Mayorga & Gleicher (2013) discuss how superimposed scatter glyphs hide point structure and how alternative representations expose it. | Measure marker footprints **before** compositing; a final raster alone cannot reveal how many opaque points coincide. Do not apply the paper's abstraction/subsampling automatically. |
| Data–ink/minimalism | Franconeri et al. (2021) review visual communication and discuss the ambiguity of “ink” and contextual effects of removing graphical elements. | Ink coverage is a visual-weight descriptor, not a data–ink ratio or an optimization objective. |

Sources (primary research and author/research-group material):

- [Rosenholtz et al., Measuring visual clutter, 2007](https://pubmed.ncbi.nlm.nih.gov/18217832/), DOI 10.1167/7.2.17; [MIT explanation and software](https://persci.mit.edu/research/clutter).
- [Chu et al., What Makes a Visualization Image Complex?, version 3, 2025](https://arxiv.org/html/2510.08332v3).
- [Mayorga & Gleicher, Splatterplots: Overcoming Overdraw in Scatter Plots, 2013](https://pmc.ncbi.nlm.nih.gov/articles/PMC4048834/), DOI 10.1109/TVCG.2013.65.
- [Franconeri et al., The Science of Visual Data Communication: What Works, 2021](https://journals.sagepub.com/doi/full/10.1177/15291006211051956).

Our inference from these sources: prose and a chart encode different tasks and
structures. None of the sources establishes an acceptable chart/prose ink ratio,
a general “too empty” percentage, or a minimum number of displayed data points.
A large ratio difference merits looking at the image; it is not sufficient
reason to warn, pad a chart with decoration, remove observations, or alter axes.

## Implemented measurements

Browser implementation: `web/src/visual-density.js`, `figure-density.js`,
`figure-checks.js`. All measurements use the physical figure dimensions;
UI zoom, screen DPR, the preview grid and article-page margins are excluded.
Each panel is evaluated independently, including within mixed grids.

### Ink and body comparison: context only

Rasterize the panel SVG at **144 dpi** (2 samples per physical point), on white;
normalize the renderer's canvas background to white. Retain axes, tick labels,
legend, data and chart gridlines as visible ink. This is whole-panel coverage,
not occupancy of the plotting rectangle and not a measure of informative ink.

For RGBA pixel values normalized to [0,1], define contrast
`c = alpha * (1 - (0.2126 R + 0.7152 G + 0.0722 B))`.

- Foreground/ink fraction: fraction of samples with `c >= 0.08`.
- Mean contrast: mean `c`, retaining antialiasing and light-tone contributions.
- Edge-transition fraction: differing neighboring foreground-mask pairs divided
  by all horizontal/vertical neighboring pairs. This is a simple binary edge
  descriptor, **not** Canny edge density, Feature Congestion or entropy.

The body reference re-typesets a **16-line strip** of the template's sample
paragraph prose using its packaged font, physical type size, leading and nominal
article-column width. Words wrap naturally, without full justification; short
sample text repeats to fill the strip. Exclude headings, references, captions,
figures, paragraph gaps, paper borders and decorative UI backgrounds. This is a
**representative body sample**, not an exact raster capture of the laid-out
article or of its narrow wrapped paragraphs. The UI calls it “Body reference ink”.

`ink_to_body_ratio = panel ink fraction / reference ink fraction`.
A ratio is absent when either measurement is unavailable. Never interpret 1× as
an ideal. The same ink coverage can have very different spatial arrangement;
solid bars can legitimately use more ink than thin lines. Color and threshold
choices also affect coverage. The reference is illustrative prose, not user data.

Raster diagnostics failing do not invalidate an otherwise valid chart. Record
`status: not_checked` and the reason; do not replace missing measurements with 0.
Keep reported method, resolution, thresholds and limitations with the numbers.

### Crowding: marker overdraw plus existing legibility checks

Sample actual filled SVG marker paths within the plot rectangle at 144 dpi.
Let `A_sum` be the sum of individually sampled mark areas and `A_union` their
union. Geometric overdraw is `1 - A_union / A_sum`; also record the fraction of
visible marks sharing at least one sampled location with another mark.

Warn with `panel_N.mark_overdraw` only when **all** hold:

- At least 20 marks have a nonzero sampled footprint.
- At least 25% of summed marker area is redundant under the union.
- At least 30% of visible markers share a sampled location.

The conjunction avoids treating every crossing or tiny sample as crowding. It
can still flag intentional dense clusters or repeated coordinates; these may be
the scientific finding. Subpixel markers can escape this measurement; invisible
marker/minimum-text checks and visual review remain necessary. Legend handles,
bar fill and chart gridlines do not create a marker warning. Line-line occlusion,
semantic redundancy and task-specific cluster separability are not measured.

Existing text collision/clipping, print-size typography and plotting-area checks
remain independent. These direct signals are useful even when total ink is low.

### Sparsity: recoverable physical space

The existing `panel_N.space_utilization` rule uses a 48×36 plotting-area occupancy
map, reserving 3 mm around data paths, markers, bars and legends. Axes/gridlines
cannot disguise unused data space. Require **all** of:

- Plot area ≥ 5,000 mm²; unoccupied fraction ≥ 65%.
- Largest empty rectangle ≥ 24% of plot area and ≥ 1,800 mm².
- Both sides of that rectangle ≥ 20 mm.

It is a conservative size-reduction suggestion, not a rule to fill every gap.
Small panels are exempt. Large intentional empty regions, outlier separation,
uncertainty or a scientifically meaningful zero can justify keeping the layout.
No bounding-box or ink measurement proves a region is scientifically dispensable.

## Agent actions

Read measurements and affected panel/region before changing anything. Prefer a
local style change whose effect can be inspected: resize markers, adjust labels,
or propose more panel space for crowding; propose a smaller physical canvas for
large empty areas while retaining readable text. Preserve user-selected settings
unless changes are authorized. Re-render and inspect at final print size.

Preserve every observation and its ordering. Do not silently aggregate, sample,
smooth, jitter, truncate axes or change ranges to appease a metric. If another
encoding is needed, explain the tradeoff and obtain authorization. Keep ordinary
breathing room. Do not add gridlines, thicker strokes, large markers or decoration
just to increase coverage or approach the body reference.

The handoff's `checks.visual_density` stores every panel's measurements, body
reference, ratios, versioned thresholds and limitations even when no warning is
raised. These are browser measurements; the Python report does not implement
this new raster/marker diagnostic. Re-check the actual output renderer and data.

## Validation boundary and next calibration step

Current tests establish geometric behavior and failure handling, not human
judgment validity: coincident/dense marks versus separated marks, high-fill bars
without spurious overdraw, compact versus oversized sparse plots, grid isolation,
zoom invariance, handoff preservation, and failed raster measurements.

Before strengthening thresholds, build a labeled set of our supported plots at
fixed physical sizes with varied series counts, outliers, marker shapes, fills,
label lengths and intentional whitespace. Ask reviewers separately about label
reading, series/point discrimination and needless space; measure false positives
and task errors. Calibrate on one subset and evaluate on a held-out subset,
stratified by chart type. Compare against real FC/SE implementations if their
benefit justifies their complexity. Do not call the present defaults calibrated.
