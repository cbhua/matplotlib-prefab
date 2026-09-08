"""The committed proof sheet in tests/output/ must match tests/data/ and the profile.

These are the tests that make ``tests/output/`` trustworthy as a reference. If
someone edits the style profile or a prefab spec and does not re-run
``python tests/render_gallery.py``, the pictures in the repository no longer show
the settings in the repository — and one of these fails saying so.
"""

import json
import os
import subprocess
import sys

import pytest

import figure_core
import inspect_figure
import render_gallery
from helpers import CASES, DATA_DIR, DEFAULT_PROFILE, OUTPUT_DIR, case

RERUN = "run `python tests/render_gallery.py` to regenerate tests/output/"
DELIVERABLES = ("figure.pdf", "figure.png", "spec.json", "profile.resolved.json", "report.json")


def committed(name, filename):
    return os.path.join(OUTPUT_DIR, name, filename)


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def test_every_data_file_is_a_described_case():
    on_disk = {
        os.path.splitext(entry)[0]
        for entry in os.listdir(DATA_DIR)
        if entry.endswith(".json")
    }
    assert on_disk == set(CASES), (
        "tests/data/ and render_gallery.CASES disagree; every prefab spec needs a "
        "one-line description saying which profile values it lets you judge"
    )


def test_every_case_describes_what_it_shows():
    for name in CASES:
        assert render_gallery.CASES[name].strip()
        assert os.path.isfile(case(name))


def test_cases_cover_both_kinds_and_the_style_edges():
    kinds = {load(case(name))["kind"] for name in CASES}
    assert kinds == {"line", "bar"}

    profile = figure_core.load_profile(DEFAULT_PROFILE)
    widest = max(
        len(load(case(name))["series"])
        for name in CASES
        if load(case(name))["kind"] == "line"
    )
    assert widest > len(profile["colors"]["categorical"]), (
        "no prefab case pushes past the palette, so nothing shows whether the "
        "dash-pattern fallback stays readable"
    )

    bar_values = [load(case(name))["values"] for name in CASES if load(case(name))["kind"] == "bar"]
    assert any(min(values) < 0 for values in bar_values), "no bar case crosses zero"
    assert any(min(values) >= 0 for values in bar_values), "no all-positive bar case"


@pytest.mark.parametrize("name", CASES)
def test_case_has_a_committed_render(name):
    for filename in DELIVERABLES:
        path = committed(name, filename)
        assert os.path.isfile(path), "%s missing; %s" % (path, RERUN)
        assert os.path.getsize(path) > 0


@pytest.mark.parametrize("name", CASES)
def test_committed_render_used_the_current_profile(name):
    assert load(committed(name, "profile.resolved.json")) == load(DEFAULT_PROFILE), (
        "tests/output/%s was rendered with a different profile than the one in the "
        "repository; %s" % (name, RERUN)
    )


@pytest.mark.parametrize("name", CASES)
def test_committed_render_used_the_current_data(name):
    assert load(committed(name, "spec.json")) == figure_core.validate_spec(load(case(name))), (
        "tests/output/%s was rendered from a different spec than tests/data/%s.json; %s"
        % (name, name, RERUN)
    )


@pytest.mark.parametrize("name", CASES)
def test_committed_report_is_clean_and_still_open_on_visual_review(name):
    report = load(committed(name, "report.json"))
    assert report["counts"]["fail"] == 0, "tests/output/%s has failing checks" % name
    assert inspect_figure.check_outputs  # the report came from this checker
    visual = next(entry for entry in report["checks"] if entry["id"] == "visual_review")
    assert visual["status"] == inspect_figure.NOT_CHECKED


@pytest.mark.parametrize("name", CASES)
def test_committed_png_matches_the_profile_geometry(name):
    profile = figure_core.load_profile(DEFAULT_PROFILE)
    width_in, height_in = figure_core.figure_size_inches(profile)
    dpi = profile["output"]["png_dpi"]
    size = inspect_figure.png_pixel_size(committed(name, "figure.png"))
    assert size is not None
    assert abs(size[0] - width_in * dpi) <= 1, "%s; %s" % (size, RERUN)
    assert abs(size[1] - height_in * dpi) <= 1, "%s; %s" % (size, RERUN)


def test_index_lists_every_case_with_its_picture():
    path = os.path.join(OUTPUT_DIR, "index.md")
    assert os.path.isfile(path), RERUN
    with open(path, encoding="utf-8") as handle:
        index = handle.read()
    for name in CASES:
        assert "## %s" % name in index, "%s is missing from the proof sheet; %s" % (name, RERUN)
        assert "(%s/figure.png)" % name in index
    # The values you are meant to be judging are printed next to the pictures.
    for key, _value in render_gallery.profile_summary(figure_core.load_profile(DEFAULT_PROFILE)):
        assert key in index


def test_index_shows_the_profile_values_actually_in_force():
    with open(os.path.join(OUTPUT_DIR, "index.md"), encoding="utf-8") as handle:
        index = handle.read()
    profile = figure_core.load_profile(DEFAULT_PROFILE)
    for key, value in render_gallery.profile_summary(profile):
        assert "| `%s` | %s |" % (key, value) in index, (
            "the proof sheet advertises a stale value for %s; %s" % (key, RERUN)
        )


def test_index_links_resolve():
    import re

    with open(os.path.join(OUTPUT_DIR, "index.md"), encoding="utf-8") as handle:
        index = handle.read()
    for _label, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", index):
        if target.startswith(("http://", "https://", "#")):
            continue
        assert os.path.exists(os.path.join(OUTPUT_DIR, target)), target


def test_gallery_script_rejects_an_unknown_case():
    result = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(OUTPUT_DIR), "render_gallery.py"),
         "--case", "no-such-case"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "no-such-case" in result.stderr
    assert "known cases" in result.stderr
