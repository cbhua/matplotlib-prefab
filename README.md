# Matplotlib Prefab

An agent-facing skill for producing publication-style matplotlib figures: give it
data and it renders a single-column, single-panel figure at a fixed physical size,
then checks the result and tells you what it could not check.

The previous version of this repository — a static gallery of notebook templates —
has been removed. It remains in the git history at commit `a3f6dfb` if you need it.

```
README.md
pyproject.toml
skills/scientific-figures/   the skill: SKILL.md, scripts, templates, references, profile
tests/                       prefab data, the proof sheet, and the behaviour tests
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

Scatter, histogram, heatmap, 3D, multi-panel and two-column figures are
deliberately out of scope for now; they will arrive as new templates and profiles.

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

No LaTeX installation is required — maths labels use matplotlib mathtext.

## Tests

```sh
.venv/bin/pip install pytest pypdf
.venv/bin/python -m pytest
```

`tests/` is both the test suite and the worked reference:

```
tests/data/            prefab specs — the input format, by example
tests/render_gallery.py  renders them all; regenerates the proof sheet
tests/output/          the committed result: five files per case, plus index.md
tests/test_*.py        the behaviour tests
```

The suite checks observable behaviour: every prefab case produces every
deliverable, data order and point counts survive the drawing, the PDF page and PNG
pixel sizes match the profile, editing the profile changes both templates, bad
input fails with a message naming the field, missing glyphs and unavailable fonts
are reported rather than hidden, the skill directory still runs after being copied
elsewhere, and the committed proof sheet matches the current profile and data.

## Contact

Questions and bug reports are welcome as issues, or at cbhua@kaist.ac.kr.
