"""Every control in the panel changes the figure. No knob is decoration.

The failure this guards against is specific and easy to ship: a slider bound to
a profile field the renderer never reads. It looks like it works — the number
moves, the panel marks it as changed, the export carries it — and the figure is
identical. So each control is exercised for real: the shared renderer draws the
figure with the control's default and again with it moved, and the two SVGs must
differ.
"""

from __future__ import annotations

import copy
import json
import os
import re

import pytest

import matplotlib

matplotlib.use("Agg")

import figure_core
from conftest import GENERATED, REPO_ROOT

CONTROLS_JS = os.path.join(REPO_ROOT, "web", "src", "controls.js")


def parse_controls():
    """Read the control list out of controls.js.

    Parsed rather than duplicated: a Python copy of the list would drift, and
    then this test would be checking a list nothing renders from.
    """
    with open(CONTROLS_JS, encoding="utf-8") as handle:
        source = handle.read()
    controls = []
    for match in re.finditer(r"\{\s*path:\s*'([^']+)'(.*?)\}", source, re.S):
        path, rest = match.group(1), match.group(2)
        if "." not in path:
            continue
        entry = {"path": path}
        fallback = re.search(r"fallback:\s*'([^']+)'", rest)
        if fallback:
            entry["fallback"] = fallback.group(1)
        choices = re.search(r"choices:\s*(\w+)", rest)
        if choices or "kind: 'choice'" in rest:
            entry["kind"] = "choice"
        for name in ("min", "max", "step"):
            value = re.search(r"\b%s:\s*(-?[\d.]+)" % name, rest)
            if value:
                entry[name] = float(value.group(1))
        entry["integer"] = "integer: true" in rest
        entry["requires_title"] = "requiresTitle: true" in rest
        controls.append(entry)
    return controls


CONTROLS = parse_controls()
assert CONTROLS, "no controls could be read out of controls.js"


def base_profile():
    with open(os.path.join(GENERATED, "profiles", "single-column.json"), encoding="utf-8") as handle:
        return json.load(handle)


def spec(name):
    with open(os.path.join(GENERATED, "specs", "%s.json" % name), encoding="utf-8") as handle:
        return json.load(handle)


def moved_value(control, current):
    if control.get("kind") == "choice":
        return "bold" if str(current) != "bold" else "normal"
    low, high = control.get("min", 0.5), control.get("max", 4.0)
    # Move to whichever end is further from where it is, so the change is
    # unmistakable rather than a rounding away.
    candidate = high if abs(high - float(current)) >= abs(float(current) - low) else low
    if control.get("integer"):
        candidate = int(candidate)
    if candidate == 0 and control["path"].endswith("_pt"):
        candidate = low or 0.1
    return candidate


def read(profile, path):
    section, _, key = path.partition(".")
    return profile.get(section, {}).get(key)


def write(profile, path, value):
    section, _, key = path.partition(".")
    profile.setdefault(section, {})[key] = value


@pytest.mark.parametrize("control", CONTROLS, ids=[c["path"] for c in CONTROLS])
def test_control_changes_the_drawing(control):
    kind = "bar" if control["path"].startswith("bar.") else "line"
    source = spec("bar-signed" if kind == "bar" else "line-multi")
    if control["requires_title"]:
        # These controls are only offered when the spec has a title, and the
        # panel disables them when it does not; the drawing is exercised under
        # the condition the panel makes them available in.
        source = dict(source, title="A title")
    profile = base_profile()

    before = figure_core.render_to_svg(source, copy.deepcopy(profile))["svg"]

    current = read(profile, control["path"])
    if current is None and control.get("fallback"):
        current = read(profile, control["fallback"])
    assert current is not None, (
        "%s has no value in the profile and no fallback that does, so the panel would "
        "show an empty box" % control["path"]
    )

    edited = copy.deepcopy(profile)
    write(edited, control["path"], moved_value(control, current))
    figure_core.validate_profile(edited)
    after = figure_core.render_to_svg(source, edited)["svg"]

    assert after != before, (
        "moving %s from %r changed nothing in the rendered figure. Either the renderer "
        "does not read that field, or the control is bound to the wrong path."
        % (control["path"], current)
    )


@pytest.mark.parametrize("control", [c for c in CONTROLS if c.get("fallback")],
                         ids=[c["path"] for c in CONTROLS if c.get("fallback")])
def test_removing_an_override_falls_back_to_the_shared_field(control):
    """Reset removes the override; the shared field must take over again."""
    source = spec("line-multi")
    profile = base_profile()
    plain = figure_core.render_to_svg(source, copy.deepcopy(profile))["svg"]

    shared = read(profile, control["fallback"])
    explicit = copy.deepcopy(profile)
    write(explicit, control["path"], shared)
    same = figure_core.render_to_svg(source, explicit)["svg"]
    assert same == plain, (
        "%s set to the same value as %s must draw the same figure as leaving it out"
        % (control["path"], control["fallback"])
    )


def test_a_profile_without_any_override_still_validates_and_renders():
    """Backwards compatibility, stated as a test rather than as an intention."""
    profile = base_profile()
    for section in profile.values():
        if isinstance(section, dict):
            for key in list(section):
                if key.startswith(("size_x", "size_y", "weight_")):
                    del section[key]
    figure_core.validate_profile(profile)
    assert figure_core.render_to_svg(spec("line-multi"), profile)["svg"]


def test_title_controls_are_marked_as_needing_a_title():
    """The shipped examples have no title, so these must not look live."""
    for control in CONTROLS:
        if control["path"] in ("fonts.size_title_pt", "fonts.weight_title"):
            assert control["requires_title"], (
                "%s only affects a figure with a title; the panel must say so rather than "
                "offering a control that changes nothing" % control["path"]
            )


def test_a_titleless_spec_really_is_unaffected_by_the_title_controls():
    """The reason the panel disables them, verified rather than assumed."""
    source = spec("line-multi")
    assert not source.get("title")
    profile = base_profile()
    plain = figure_core.render_to_svg(source, copy.deepcopy(profile))["svg"]
    edited = copy.deepcopy(profile)
    write(edited, "fonts.size_title_pt", 18.0)
    write(edited, "fonts.weight_title", "bold")
    assert figure_core.render_to_svg(source, edited)["svg"] == plain


def test_the_panel_offers_every_field_the_plan_asked_for():
    paths = {control["path"] for control in CONTROLS}
    for required in (
        "fonts.size_x_label_pt", "fonts.size_y_label_pt",
        "fonts.size_xtick_pt", "fonts.size_ytick_pt",
        "fonts.size_legend_pt", "fonts.size_title_pt",
        "fonts.weight_x_label", "fonts.weight_y_label",
        "lines.data_linewidth_pt", "lines.axes_linewidth_pt",
        "lines.tick_linewidth_pt", "lines.marker_size_pt",
        "lines.tick_length_pt", "lines.tick_pad_pt",
        "axes.max_xticks", "axes.max_yticks",
        "axes.grid_alpha", "axes.grid_linewidth_pt",
        "bar.width_fraction", "bar.category_label_rotation_deg",
    ):
        assert required in paths, "the panel does not offer %s" % required
