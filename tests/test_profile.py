"""The profile is the single source of style truth: templates must not override it."""

import copy

import pytest

import figure_core
import inspect_figure
from helpers import (
    BAR_SPEC,
    LINE_CASE,
    LINE_SPEC,
    build_figure,
    case,
    check,
    load_default_profile,
    render,
)


@pytest.mark.parametrize("spec", [LINE_SPEC, BAR_SPEC], ids=["line", "bar"])
def test_edited_font_sizes_and_line_widths_reach_the_artists(spec):
    profile = load_default_profile()
    profile["fonts"]["size_axis_label_pt"] = 13.0
    profile["fonts"]["size_tick_pt"] = 11.0
    profile["fonts"]["size_title_pt"] = 15.0
    profile["lines"]["data_linewidth_pt"] = 3.3
    profile["lines"]["axes_linewidth_pt"] = 2.2

    edited = copy.deepcopy(spec)
    edited["title"] = "Title"
    fig, ax, _drawn, plt = build_figure(edited, profile)
    try:
        assert ax.xaxis.label.get_fontsize() == 13.0
        assert ax.yaxis.label.get_fontsize() == 13.0
        assert ax.title.get_fontsize() == 15.0
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            assert label.get_fontsize() == 11.0
        assert ax.spines["left"].get_linewidth() == 2.2
        if edited["kind"] == "line":
            assert ax.lines[0].get_linewidth() == 3.3
    finally:
        plt.close(fig)


@pytest.mark.parametrize("spec", [LINE_SPEC, BAR_SPEC], ids=["line", "bar"])
def test_edited_palette_reaches_the_artists(spec):
    profile = load_default_profile()
    profile["colors"]["categorical"] = ["#123456", "#654321"]
    fig, ax, _drawn, plt = build_figure(copy.deepcopy(spec), profile)
    try:
        if spec["kind"] == "line":
            assert ax.lines[0].get_color() == "#123456"
        else:
            assert ax.patches[0].get_facecolor()[:3] == pytest.approx(
                (0x12 / 255, 0x34 / 255, 0x56 / 255), abs=1e-3
            )
    finally:
        plt.close(fig)


def test_edited_canvas_size_changes_the_figure_and_the_report(tmp_path):
    profile = load_default_profile()
    profile["canvas"]["width_mm"] = 120.0
    profile["canvas"]["aspect_ratio"] = 0.5
    _, report = render(tmp_path, case(LINE_CASE), profile=profile)
    details = check(report, "canvas_size")["details"]
    assert details["width_mm"] == pytest.approx(120.0, abs=1e-3)
    assert details["actual_in"][1] == pytest.approx(details["actual_in"][0] * 0.5, abs=1e-6)
    assert check(report, "canvas_size")["status"] == inspect_figure.PASS


def test_height_is_derived_not_stored():
    profile = load_default_profile()
    width_in, height_in = figure_core.figure_size_inches(profile)
    assert height_in == pytest.approx(width_in * profile["canvas"]["aspect_ratio"])
    assert "height_mm" not in profile["canvas"]


def test_marker_shape_is_bound_to_the_series_slot():
    profile = load_default_profile()
    styles = figure_core.series_styles(3, profile)
    assert [style["color"] for style in styles] == profile["colors"]["categorical"][:3]
    assert [style["marker"] for style in styles] == profile["lines"]["markers"][:3]


def test_reused_colours_get_a_new_dash_pattern():
    profile = load_default_profile()
    n_colors = len(profile["colors"]["categorical"])
    styles = figure_core.series_styles(n_colors + 1, profile)
    assert styles[n_colors]["color"] == styles[0]["color"]
    assert styles[n_colors]["linestyle"] != styles[0]["linestyle"]


def test_style_is_local_and_does_not_leak_into_later_figures():
    import matplotlib

    profile = load_default_profile()
    profile["fonts"]["size_tick_pt"] = 31.0
    before = matplotlib.rcParams["xtick.labelsize"]
    fig, _ax, _drawn, plt = build_figure(copy.deepcopy(LINE_SPEC), profile)
    plt.close(fig)
    assert matplotlib.rcParams["xtick.labelsize"] == before


def test_profile_rejects_non_positive_geometry(tmp_path):
    for section, key, value in (
        ("canvas", "width_mm", 0.0),
        ("canvas", "aspect_ratio", -1.0),
        ("fonts", "size_axis_label_pt", 0.0),
        ("output", "png_dpi", 0.0),
    ):
        profile = load_default_profile()
        profile[section][key] = value
        with pytest.raises(figure_core.ProfileError) as excinfo:
            figure_core.validate_profile(profile)
        assert "%s.%s" % (section, key) in str(excinfo.value)


def test_profile_rejects_missing_sections():
    profile = load_default_profile()
    del profile["legend"]
    with pytest.raises(figure_core.ProfileError) as excinfo:
        figure_core.validate_profile(profile)
    assert "legend" in str(excinfo.value)


def test_profile_rejects_an_empty_palette():
    profile = load_default_profile()
    profile["colors"]["categorical"] = []
    with pytest.raises(figure_core.ProfileError):
        figure_core.validate_profile(profile)


def test_profile_rejects_a_conflicting_layout_engine():
    profile = load_default_profile()
    profile["layout"]["engine"] = "tight"
    with pytest.raises(figure_core.ProfileError) as excinfo:
        figure_core.validate_profile(profile)
    assert "constrained" in str(excinfo.value)


def test_shipped_profile_is_marked_provisional():
    profile = load_default_profile()
    assert profile["status"] == "provisional"
    assert profile["profile_version"]
