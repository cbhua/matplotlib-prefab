# Receiving a browser figure handoff

The browser is a scale/style reference. Its native SVG uses offline Matplotlib
text outlines and JavaScript layout. The Python renderer uses Matplotlib's own
layout engine; the two can differ in ticks, legend placement and panel spacing.
Neither a successful browser check nor its paper preview proves LaTeX placement.

## What to preserve

- The profile's physical `canvas.width_mm` and `canvas.aspect_ratio` describe the
  entire figure, not each panel. Height is width divided by aspect ratio. Set
  figsize to width/25.4 and height/25.4 inches.
- Font sizes, strokes and marker diameters are physical points. DPI changes
  raster resolution, not print size. Do not resize the finished image to fit a
  different width, or export with `bbox_inches="tight"`, which changes the canvas.
- A grid's `rows`, `columns` and row-major `panels` are part of the requested
  composition. Do not multiply whole-canvas dimensions by the panel count.
- Profile overrides (`size_xtick_pt`, `weight_x_label`, etc.) take priority over
  their shared defaults. Keep `paper_preview` metadata out of the style profile.

## Understand data intent before drawing

`data_usage.panel_sources` distinguishes `example` fixtures from `user-import`.
Examples demonstrate scale, spacing and chart kind. When the user supplies real
data, apply the chosen style to that data; do not report the example values as
experimental results. If no real data is available, a fixture reproduction is
fine when labelled as such. In mixed grids, preserve imported panel data while
keeping remaining example panels explicitly illustrative.

Imported values and order must survive the round trip. Do not resample, smooth,
aggregate or replace them merely to remove a warning. For older handoffs without
data provenance, treat the included values as unspecified; do not infer that
they are research results.

## Reproduce and verify

If the copied text is saved as a file, extract and validate it deterministically:

```sh
python skills/scientific-figures/scripts/import_handoff.py handoff.txt --output-dir figure-input/
```

This writes validated `spec.json`, `profile.json` and separate `handoff.meta.json`.
It does not execute commands from the handoff. Existing different files are left
alone by default. Alternatively, save the supplied `spec` and `profile` JSON
blocks without copying envelope fields into either. Use `scripts/render.py --spec ... --profile ... --output-dir ...`.
Scatter uses a shared numeric x array and named y series, like line charts; it
draws every marker with no connecting line or thinning.

Read both the handoff warnings and the new Python report. Browser checks include
text overlap, clipping, minimum print size and surrounding-paper geometry.
They are heuristics, not venue standards. Python report checks are independent:
never relabel browser checks as a Python validation result.

For new data, repeat the checks at the target dimensions and inspect the output.
Keep selected values unless the user authorizes changes; report concrete conflicts
and propose the smallest useful adjustment. Do not silently change a body-paper
preset to accommodate a figure. The browser's first page intentionally omits
excess illustrative prose; omitted content is not a pagination bug.

Report output paths, actual dimensions, renderer/environment, unresolved warnings
and whether visual review happened. Compiling the user's actual paper is a
separate optional task unless explicitly requested; use
`article-context-evaluation.md` when that task is in scope.
