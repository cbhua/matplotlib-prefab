"""End-to-end behaviour of the render pipeline and its deliverables."""

import copy
import json
import os

import pytest

import figure_core
import inspect_figure
from helpers import (
    BAR_CASE,
    CASES,
    BAR_SPEC,
    LINE_CASE,
    LINE_SPEC,
    case,
    check,
    load_default_profile,
    render,
)

DELIVERABLES = ("figure.pdf", "figure.png", "spec.json", "profile.resolved.json", "report.json")


@pytest.mark.parametrize("name", CASES)
def test_every_prefab_case_produces_every_deliverable(tmp_path, name):
    output_dir, report = render(tmp_path, case(name), subdir=name)
    for filename in DELIVERABLES:
        path = os.path.join(output_dir, filename)
        assert os.path.isfile(path), "%s was not written" % filename
        assert os.path.getsize(path) > 0
    assert report["status"] != inspect_figure.FAIL
    assert report["counts"]["fail"] == 0


@pytest.mark.parametrize("name", CASES)
def test_snapshot_is_exactly_what_was_drawn(tmp_path, name):
    output_dir, _ = render(tmp_path, case(name), subdir=name)
    with open(case(name), encoding="utf-8") as handle:
        source = json.load(handle)
    with open(os.path.join(output_dir, "spec.json"), encoding="utf-8") as handle:
        snapshot = json.load(handle)
    assert snapshot == figure_core.validate_spec(source)


def test_resolved_profile_snapshot_can_drive_a_rerender(tmp_path):
    first_dir, first = render(tmp_path, case(LINE_CASE), subdir="first")
    second_dir, second = render(
        tmp_path,
        os.path.join(first_dir, "spec.json"),
        profile=os.path.join(first_dir, "profile.resolved.json"),
        subdir="second",
    )
    assert second["status"] == first["status"]
    assert check(second, "canvas_size")["details"] == check(first, "canvas_size")["details"]
    assert check(second, "png_pixel_size")["details"] == check(first, "png_pixel_size")["details"]


def test_report_records_environment_and_reproduce_command(tmp_path):
    _, report = render(tmp_path, case(BAR_CASE))
    assert report["environment"]["matplotlib"]
    assert report["environment"]["python"]
    assert report["environment"]["resolved_fonts"]
    assert "--spec" in report["reproduce"] and "--profile" in report["reproduce"]


def test_visual_review_is_never_auto_passed(tmp_path):
    for name in CASES:
        _, report = render(tmp_path, case(name), subdir=name)
        entry = check(report, "visual_review")
        assert entry["status"] == inspect_figure.NOT_CHECKED


def test_render_only_touches_its_own_files(tmp_path):
    output_dir = os.path.join(str(tmp_path), "out")
    os.makedirs(output_dir)
    bystander = os.path.join(output_dir, "notes.md")
    with open(bystander, "w", encoding="utf-8") as handle:
        handle.write("keep me")
    render(tmp_path, case(LINE_CASE), subdir="out")
    assert open(bystander, encoding="utf-8").read() == "keep me"
    assert sorted(os.listdir(output_dir)) == sorted(DELIVERABLES + ("notes.md",))


def test_rerender_overwrites_deliverables_in_place(tmp_path):
    output_dir, _ = render(tmp_path, case(LINE_CASE), subdir="out")
    stale = os.path.join(output_dir, "report.json")
    with open(stale, "w", encoding="utf-8") as handle:
        handle.write("{}")
    render(tmp_path, case(LINE_CASE), subdir="out")
    with open(stale, encoding="utf-8") as handle:
        assert json.load(handle)["checks"]


# --------------------------------------------------------------------------
# Data fidelity
# --------------------------------------------------------------------------

def test_line_series_keep_order_and_every_point(tmp_path):
    _, report = render(tmp_path, case(LINE_CASE))
    entry = check(report, "line_data_integrity")
    assert entry["status"] == inspect_figure.PASS
    with open(case(LINE_CASE), encoding="utf-8") as handle:
        source = json.load(handle)
    assert entry["details"]["n_points"] == len(source["x"])
    assert entry["details"]["n_series"] == len(source["series"])
    assert [item["name"] for item in report["drawn"]["series"]] == [
        item["name"] for item in source["series"]
    ]


def test_multi_series_styles_are_distinct_and_legend_is_drawn(tmp_path):
    _, report = render(tmp_path, case(LINE_CASE))
    assert check(report, "series_distinguishable")["status"] == inspect_figure.PASS
    assert check(report, "legend_present")["status"] == inspect_figure.PASS
    assert report["drawn"]["legend_drawn"] is True
    styles = [tuple(sorted(item["style"].items())) for item in report["drawn"]["series"]]
    assert len(set(styles)) == len(styles)


def test_single_series_line_omits_the_legend_by_default(tmp_path):
    _, report = render(tmp_path, copy.deepcopy(LINE_SPEC))
    assert report["drawn"]["legend_drawn"] is False
    assert check(report, "legend_present")["status"] == inspect_figure.PASS


def test_markers_are_thinned_but_no_data_point_is_dropped(tmp_path):
    _, report = render(tmp_path, case(LINE_CASE))
    assert report["drawn"]["marker_every"] > 1
    assert check(report, "line_data_integrity")["status"] == inspect_figure.PASS


def test_bar_keeps_category_order_and_spans_zero(tmp_path):
    _, report = render(tmp_path, case(BAR_CASE))
    assert check(report, "bar_category_order")["status"] == inspect_figure.PASS
    zero = check(report, "bar_zero_in_range")
    assert zero["status"] == inspect_figure.PASS
    low, high = zero["details"]["ylim"]
    assert low <= 0.0 <= high
    assert check(report, "bar_count")["details"]["n_bars"] == 5


@pytest.mark.parametrize(
    "values",
    [[1.0, 2.0, 3.0], [-1.0, -2.0, -3.0], [1.0, -2.0, 3.0], [0.0, 0.0, 0.0]],
)
def test_bar_y_range_always_contains_zero(tmp_path, values):
    spec = copy.deepcopy(BAR_SPEC)
    spec["values"] = values
    _, report = render(tmp_path, spec)
    low, high = check(report, "bar_zero_in_range")["details"]["ylim"]
    assert low <= 0.0 <= high


def test_all_positive_bars_sit_exactly_on_zero(tmp_path):
    spec = copy.deepcopy(BAR_SPEC)
    spec["values"] = [1.0, 2.0, 3.0]
    _, report = render(tmp_path, spec)
    low, _high = check(report, "bar_zero_in_range")["details"]["ylim"]
    assert low == 0.0


def test_single_series_bars_share_one_colour(tmp_path):
    profile = load_default_profile()
    _, report = render(tmp_path, case(BAR_CASE), profile=profile)
    assert report["drawn"]["color"] == profile["colors"]["categorical"][0]


# --------------------------------------------------------------------------
# Failure modes that must not report success
# --------------------------------------------------------------------------

def test_too_many_series_is_a_clear_error_not_a_silent_cycle(tmp_path):
    profile = load_default_profile()
    capacity = len(profile["colors"]["categorical"]) * len(profile["lines"]["dash_patterns"])
    spec = copy.deepcopy(LINE_SPEC)
    spec["series"] = [
        {"name": "s%d" % i, "y": [float(i)] * 4} for i in range(capacity + 1)
    ]
    with pytest.raises(figure_core.SpecError) as excinfo:
        render(tmp_path, spec)
    message = str(excinfo.value)
    assert str(capacity) in message and "distinguishable" in message


def test_series_at_exactly_the_style_capacity_still_render(tmp_path):
    profile = load_default_profile()
    capacity = len(profile["colors"]["categorical"]) * len(profile["lines"]["dash_patterns"])
    spec = copy.deepcopy(LINE_SPEC)
    spec["series"] = [{"name": "s%d" % i, "y": [float(i)] * 4} for i in range(capacity)]
    _, report = render(tmp_path, spec)
    assert check(report, "series_distinguishable")["status"] == inspect_figure.PASS


def test_missing_glyphs_are_reported_as_a_failure(tmp_path):
    spec = copy.deepcopy(BAR_SPEC)
    spec["x_label"] = "方法"  # CJK: absent from DejaVu Sans
    _, report = render(tmp_path, spec)
    entry = check(report, "glyph_coverage")
    assert entry["status"] == inspect_figure.FAIL
    assert report["status"] == inspect_figure.FAIL
    assert "方" in entry["details"]["missing"][0]["missing_characters"]


def test_long_labels_are_not_reported_as_all_clear(tmp_path):
    spec = copy.deepcopy(BAR_SPEC)
    spec["categories"] = [
        "a very long category name one",
        "a very long category name two",
        "a very long category name three",
    ]
    _, report = render(tmp_path, spec)
    assert report["status"] in (inspect_figure.WARN, inspect_figure.FAIL)
    flagged = {
        entry["id"]
        for entry in report["checks"]
        if entry["status"] in (inspect_figure.WARN, inspect_figure.FAIL)
    }
    assert flagged & {"tick_label_overlap", "text_within_canvas"}


def test_requesting_an_unavailable_font_warns_rather_than_pretending(tmp_path):
    profile = load_default_profile()
    profile["fonts"]["family"] = "Definitely Not An Installed Font"
    _, report = render(tmp_path, case(BAR_CASE), profile=profile)
    entry = check(report, "font_resolution")
    assert entry["status"] == inspect_figure.WARN
    assert "Definitely Not An Installed Font" in entry["message"]
