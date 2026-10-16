# Bundled renderer and verification

Use this for the Matplotlib execution path. General constraints are in
`../SKILL.md`; reference values are in `conference-presets/`. Rendering mechanics
and optional role overrides are described in [design-rules.md](design-rules.md).

## Input and outputs

Read [input-schema.md](input-schema.md) before creating a spec. The portable
`../assets/examples/line.json` is a synthetic example, not experimental evidence.
Store the real spec durably beside the user's work.

```sh
python <skill-directory>/scripts/render.py \
  --preset iclr2026-first --spec <spec.json> --output-dir <output-directory>
```

`--profile <full-profile.json>` overrides drawing defaults, while `--preset`
still supplies the body/template reference for checks. Without either option,
`profiles/single-column.json` is the generic rendering fallback. Explicitly use
`--text-wrap off` with a preset when the figure will not have prose beside it.
This changes only the width-check assumption, not the figure dimensions. For a
full-width figure, also set the actual canvas width in a copied profile.

The command writes five files, replacing only those named files:

| File | Purpose |
| --- | --- |
| `figure.pdf` | Vector deliverable at the resolved canvas size |
| `figure.png` | Raster preview; DPI changes pixels, not physical type size |
| `spec.json` | Validated data and labels exactly as drawn |
| `profile.resolved.json` | Full settings actually used, including inherited defaults |
| `report.json` | Checks, environment/fonts, reference snapshot and reproduce command |

Exit `0` means rendered without failed checks (warnings may remain); `1` means
failed checks; `2` means rejected spec/profile. Fix named input errors rather
than weakening validation. The process never silently repairs data. A runtime
layout error can leave partial outputs; only deliver files from a completed run.

Use the report's reproduce command with the saved spec/profile. The conference
reference snapshot preserves which recommendations were evaluated. Re-running
against a subsequently edited packaged preset re-evaluates the new policy;
compare snapshots before claiming the diagnostics are identical.

## Coverage and review

| Check family | Python renderer | Browser preview / further review |
| --- | --- | --- |
| Canvas/PDF/PNG size, artist fonts, data/order, bar zero baseline, glyphs, style distinguishability | Automatic | Renderer-specific; repeat after export |
| Paper-relative type, equal X/Y label size, wrapped width, stroke floor | Automatic with `--preset` | Browser evaluates its own current rule registry |
| Label collisions, clipping, plot area, grid decoration overlap | Geometric heuristics | Review actual export; solvers differ |
| Legend/data occlusion | Explicitly not checked | Browser samples data under protected legend rectangle; inspect final export |
| Ink/body ratio, marker overdraw, recoverable space, bar distribution | Explicitly not checked | Browser measurements plus scientific-context review |
| Caption/prose collisions, footer fit, actual insertion scale | Explicitly not checked | Browser approximates placement; real document evaluation verifies placement |
| Scientific meaning, task suitability, aesthetics, print/color readability | Visual/context review | Never inferred from a clean report |

Read each warning's measured values and affected panels. Shared type warnings
are grouped by role. A preset reports recommendations as warnings; malformed
data, missing glyphs or broken output contracts can fail independent checks.
No warning automatically authorizes changing data or a user-selected style.

For grids retain rows, columns, row-major panel order and shared physical type
sizes. Canvas dimensions include every panel and any separate legend. Explicit
outside sides must be preserved; inability to fit is an error, not permission
to shrink type or change the side silently.

Do not use `bbox_inches="tight"` or resize the export without rechecking final
dimensions and text sizes. Layout runs under `constrained` only; do not combine
it with `tight_layout` or `subplots_adjust`. Templates consume the profile and
must not acquire competing style defaults.

Open the exported preview and inspect it with the target body-text scale in
mind. Automatic `visual_review` remains `not_checked`; state separately what you
looked at. If no image can be opened, say the visual review was not performed.
For actual article placement read [article-context-evaluation.md](article-context-evaluation.md).
