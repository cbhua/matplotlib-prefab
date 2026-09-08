# Figure spec — the input contract

A figure spec is one JSON object. It is the whole input: everything about *what*
is drawn lives here, everything about *how* it looks lives in the profile
(`references/profiles/single-column.json`).

`render.py` validates the spec before it draws anything. Validation is strict on
purpose: a spec that is wrong produces an error naming the offending field, never
a figure plus a clean report.

## Common fields

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `schema_version` | string | yes | Must be `"1"`. Any other value is an error. |
| `kind` | string | yes | `"line"` or `"bar"`. Nothing else is supported yet. |
| `x_label` | string | yes | X axis label. May be `""` to leave the axis unlabelled. |
| `y_label` | string | yes | Y axis label. May be `""`. |
| `title` | string or `null` | no | Panel title. Omitted by default — in a paper the caption usually carries it. |

Unknown top-level fields are **rejected**, so a misspelled `y_lable` fails loudly
instead of being silently dropped.

## `kind: "line"`

| Field | Type | Meaning |
| --- | --- | --- |
| `x` | array of numbers | Shared x values, at least one. |
| `series` | array of objects | One or more series, each `{"name": string, "y": array of numbers}`. |

Rules:

* every `series[i].y` must have exactly the same length as `x`;
* `series[i].name` must be unique — it is the legend entry;
* **order is preserved.** Points are not sorted, smoothed, resampled, deduplicated
  or aggregated. What you send is what is plotted, in the order you sent it. If x
  is not monotonic the line will double back, which is your data, not a bug;
* series count is capped by what the profile can distinguish — see *Too many
  series* below.

```json
{
  "schema_version": "1",
  "kind": "line",
  "x_label": "Training epoch",
  "y_label": "Validation loss",
  "x": [0, 10, 20, 30],
  "series": [
    {"name": "Baseline", "y": [1.9, 1.2, 0.8, 0.6]},
    {"name": "Ours", "y": [1.8, 0.9, 0.5, 0.4]}
  ]
}
```

## `kind: "bar"`

| Field | Type | Meaning |
| --- | --- | --- |
| `categories` | array of strings | Unique category names, in the order they should appear. |
| `values` | array of numbers | One value per category, same length as `categories`. |

Rules:

* one series only, vertical bars, one bar per category;
* category order is preserved exactly;
* negative values are allowed. The y range always contains zero and the zero
  baseline is always drawn, so bar lengths stay comparable;
* **this is not a histogram.** `values` are plotted as given; nothing is binned or
  counted. To show a distribution you would need a histogram, which this version
  does not implement.

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

## Numbers

A value is valid when it is a JSON number that is finite and not a boolean.
Rejected: strings (`"1.0"`), `null`, `true`/`false`, and the non-standard JSON
literals `NaN`, `Infinity`, `-Infinity`. Drop or impute missing points in your own
pipeline before writing the spec — the skill will not guess what a gap means.

## Text and maths

Labels, series names and category names are used verbatim; nothing is
capitalised, truncated or reworded.

Maths uses matplotlib's built-in **mathtext**, written between dollar signs:
`"$\\alpha_{i}$"`, `"Time $t$ (s)"`, `"$\\mathrm{m\\,s^{-2}}$"`. Remember that a
JSON string needs the backslash doubled. Mathtext covers a useful subset of LaTeX
maths and needs **no LaTeX installation**; it is not guaranteed to match a
specific journal template glyph for glyph. Ordinary words stay upright; italics
are for maths variables, which is what mathtext does by default.

Non-ASCII text (CJK, accented characters, symbols) is allowed, but it only renders
if the font in the profile actually contains those characters. The `glyph_coverage`
check fails the report when it does not, rather than letting them export as empty
boxes. To use CJK, install a font that covers it and set `fonts.family` (or add it
to `fonts.fallbacks`) in your profile. The skill does not download or bundle fonts.

## Errors you should expect

| Situation | Result |
| --- | --- |
| Unknown `kind` (`"scatter"`, `"hist"`, …) | Error naming the kind and listing what is supported |
| Unknown or misspelled field | Error naming the field |
| Empty `x`, `series`, `categories` or `values` | Error naming the field |
| `y` length ≠ `x` length | Error stating both lengths |
| `values` length ≠ `categories` length | Error stating both lengths |
| Non-numeric or non-finite value | Error with the exact index, e.g. `spec.series[0].y[3]` |
| Duplicate series name or category | Error naming the duplicate |
| Malformed JSON | Error naming the file and the parse position |

Every one of these exits with status `2` and writes nothing. There is no partial
output and no success report.

### Too many series

Styles come from `profile.colors.categorical` × `profile.lines.dash_patterns`.
The first *N* series get distinct colours; beyond that the dash pattern changes so
reused colours stay separable. Past that product there is no honest way to keep
them apart, so the render fails with a message giving the capacity. Split the
figure, plot fewer series, or extend the palette in the profile — the skill will
not quietly recycle styles into an unreadable figure.
