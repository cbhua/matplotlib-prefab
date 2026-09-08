# tests

Two jobs in one directory: the behaviour tests, and the worked reference for
using the skill.

```
data/               prefab specs — the input format, by example
render_gallery.py   renders every spec with the current profile
output/             the committed result: five files per case, plus index.md
test_*.py           the behaviour tests
helpers.py          shared fixtures; conftest.py puts the skill on sys.path
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

## Why the output is committed

So the pictures can be reviewed in the repository and in a diff, and so the
preset values are visible without running anything. `test_gallery.py` keeps that
honest: it compares each committed render against the current profile and the
current spec, and fails with `run python tests/render_gallery.py` if they have
drifted apart.

## Running the tests

```sh
python -m pytest            # from the repository root
```

Tests render into pytest's `tmp_path`; only `render_gallery.py` writes `output/`.
`pypdf` is needed for the page-size assertions (`pip install pytest pypdf`).
