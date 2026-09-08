"""Shared helpers for the behaviour tests.

Test data comes from ``tests/data/``: the same specs the proof sheet in
``tests/output/`` is built from, so the pictures you look at and the figures the
tests assert on are never two different things.
"""

import copy
import json
import os

from conftest import REPO_ROOT, SKILL_ROOT  # noqa: F401

import figure_core
import render as render_module
import render_gallery

DATA_DIR = render_gallery.DATA_DIR
OUTPUT_DIR = render_gallery.OUTPUT_DIR
CASES = render_gallery.case_names()
DEFAULT_PROFILE = figure_core.default_profile_path(SKILL_ROOT)

# The two cases most tests exercise: a multi-series line and a bar chart that
# crosses zero.
LINE_CASE = "line-multi"
BAR_CASE = "bar-signed"


def case(name):
    """Path to a prefab spec in tests/data/."""
    return render_gallery.spec_path(name)


def load_default_profile():
    return copy.deepcopy(figure_core.load_profile(DEFAULT_PROFILE))


def write_json(tmp_path, name, payload):
    path = os.path.join(str(tmp_path), name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    return path


def render(tmp_path, spec, profile=None, subdir="out"):
    """Render a spec dict (or a path) into a temporary directory.

    Tests always render into ``tmp_path``; only ``render_gallery.py`` writes the
    committed ``tests/output/`` tree.
    """
    spec_path = spec if isinstance(spec, str) else write_json(tmp_path, "spec-input.json", spec)
    profile_path = (
        profile
        if profile is None or isinstance(profile, str)
        else write_json(tmp_path, "profile-input.json", profile)
    )
    output_dir = os.path.join(str(tmp_path), subdir)
    report = render_module.render(spec_path, output_dir, profile_path)
    return output_dir, report


def build_figure(spec_dict, profile):
    """Draw in-process and hand back the live figure for artist-level assertions."""
    import matplotlib.pyplot as plt

    spec = figure_core.validate_spec(spec_dict)
    template = render_module.load_template(spec["kind"])
    with figure_core.style_context(profile):
        fig, ax = figure_core.create_figure(profile)
        drawn = template.draw(ax, spec, profile)
        fig.draw_without_rendering()
    return fig, ax, drawn, plt


def check(report, check_id):
    for entry in report["checks"]:
        if entry["id"] == check_id:
            return entry
    raise AssertionError("report has no check %r" % check_id)


# Minimal hand-written specs, for contract and style assertions where prefab data
# would only add noise.
LINE_SPEC = {
    "schema_version": "1",
    "kind": "line",
    "x_label": "x",
    "y_label": "y",
    "x": [0, 1, 2, 3],
    "series": [{"name": "a", "y": [1.0, 2.0, 1.5, 3.0]}],
}

BAR_SPEC = {
    "schema_version": "1",
    "kind": "bar",
    "x_label": "category",
    "y_label": "value",
    "categories": ["a", "b", "c"],
    "values": [1.0, -2.0, 3.0],
}
