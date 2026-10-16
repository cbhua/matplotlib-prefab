"""The portable ICLR skill and the current web calibration must not drift."""

import copy
import json
from pathlib import Path

import pytest

import conference_presets
from conftest import REPO_ROOT, needs_browser, needs_fonts

pytestmark = [pytest.mark.web, needs_browser, needs_fonts]
SKILL = Path(REPO_ROOT) / "skills/scientific-figures"


def test_packaged_iclr_values_match_web_sources(lab):
    preset, profile, _ = conference_presets.load_preset("iclr2026-first", str(SKILL))
    web = lab.page.evaluate("""async () => {
      const [{EXPERIENCE_RULES:e},{DENSITY_RULES:d},{VISUAL_DENSITY_RULES:v},
        {LEGEND_OVERLAP_RULES:l},{FIGURE_CHECK_RULES:f},{PAPER_CHECK_RULES:p},papers] = await Promise.all([
        import('/src/experience-rules.js'),import('/src/figure-density.js'),
        import('/src/visual-density.js'),import('/src/figure-occlusion.js'),
        import('/src/figure-checks.js'),import('/src/paper-checks.js'),
        fetch('/presets/papers.json').then(r=>r.json())]);
      return {e,d,v,l,f,p,paper:papers.presets.find(p=>p.id==='iclr2026')};
    }""")
    paper = web["paper"]
    for key in ("body_size_pt", "body_leading_pt", "caption_size_pt"):
        assert preset["paper"][key] == paper[key]
    for key in ("width_mm", "height_mm", "left_mm", "top_mm"):
        assert preset["paper"]["body_" + key] == paper["body"][key]
    assert profile["canvas"]["width_mm"] == pytest.approx(paper["body"]["width_mm"] * preset["placement"]["figure_body_width_ratio"])
    assert profile["canvas"]["aspect_ratio"] == paper["figure_aspect_ratio"]
    t = web["e"]["typography"]
    body = paper["body_size_pt"]
    for role in ("axis_labels", "tick_labels"):
        for source, target in (("recommended_pt", "target_body_ratio"), ("minimum_pt", "minimum_body_ratio"), ("maximum_pt", "maximum_body_ratio")):
            assert t[role][source] == pytest.approx(preset["rules"][role][target] * body)
    assert preset["rules"]["axis_labels"]["equal_size_tolerance_pt"] == t["axis_labels"]["equal_size_tolerance_pt"]
    for key in ("target_axis_label_ratio", "axis_label_tolerance_pt"):
        assert preset["rules"]["tick_labels"][key] == t["tick_labels"][key]
    for key in ("minimum_body_ratio", "maximum_body_ratio"):
        assert preset["rules"]["legend"][key] == t["legend"][key]
    for key in ("minimum_recommended_ratio", "maximum_recommended_ratio", "caption_cramped_below_ratio"):
        assert preset["rules"]["wrapped_figure"][key] == web["e"]["wrapped_figure"][key]
    assert preset["rules"]["wrapped_figure"]["minimum_remaining_text_mm"] == web["p"]["minimumWrapTextMm"]
    assert preset["rules"]["strokes"]["minimum_checked_pt"] == web["f"]["minimumStrokePt"]
    for key, source in (("data_linewidth_pt", "data_default_pt"), ("axes_linewidth_pt", "axes_default_pt"), ("tick_linewidth_pt", "tick_default_pt")):
        assert profile["lines"][key] == web["e"]["strokes"][source]
    b = preset["browser_diagnostics"]
    assert b["legend_overlap"] == {"dpi": web["l"]["dpi"], "minimum_alpha": web["l"]["minimumAlpha"]}
    assert b["minimum_other_text_pt"] == web["f"]["minimumTextPt"]
    assert b["minimum_plot_fraction"] == web["f"]["minimumPlotFraction"]
    for key, source in (("dpi", "dpi"), ("foreground_contrast", "foregroundContrast")):
        assert b["visual_density"][key] == web["v"][source]
    for key, source in (("minimum_visible_marks", "minimumMarks"), ("minimum_overdraw_fraction", "minimumOverdraw"), ("minimum_overlapping_marks_fraction", "minimumOverlappingMarks")):
        assert b["marker_overdraw"][key] == web["v"][source]
    for key, source in (("columns", "columns"), ("rows", "rows"), ("breathing_room_mm", "breathingRoomMm"), ("minimum_plot_area_mm2", "minimumPlotAreaMm2"), ("minimum_empty_fraction", "minimumEmptyFraction"), ("minimum_empty_rectangle_fraction", "minimumEmptyRectangleFraction"), ("minimum_empty_rectangle_mm2", "minimumEmptyRectangleMm2"), ("minimum_empty_side_mm", "minimumEmptySideMm")):
        assert b["recoverable_space"][key] == web["d"][source]


@pytest.mark.parametrize("changes", [{}, {"size_x_label_pt": 10}, {"size_axis_label_pt": 8.5}, {"size_axis_label_pt": 3}, {"size_tick_pt": 7}, {"size_legend_pt": 11}])
def test_browser_and_skill_typography_agree_for_iclr(lab, changes):
    preset, profile, _ = conference_presets.load_preset("iclr2026-first", str(SKILL))
    spec = json.loads((SKILL / "assets/examples/line.json").read_text())
    profile["fonts"].update(changes)
    python = conference_presets.evaluate_preset(copy.deepcopy(spec), profile, preset)
    browser = lab.page.evaluate("""async ([profile,spec,body]) => {
      const {evaluateTypography} = await import('/src/typography-checks.js');
      return evaluateTypography({preview_settings:{body_size_pt:body}},profile,spec);
    }""", [profile, spec, preset["paper"]["body_size_pt"]])
    names = {"paper.size_x_label_pt": "reference.x_label", "paper.size_y_label_pt": "reference.y_label",
             "paper.size_xtick_pt": "reference.xtick", "paper.size_ytick_pt": "reference.ytick",
             "paper.size_legend_pt": "reference.legend", "paper.axis_label_consistency": "reference.axis_label_consistency"}
    browser_warns = {names[c["id"]] for c in browser}
    python_warns = {c["id"] for c in python.checks if c["status"] == "warn" and c["id"] in names.values()}
    assert python_warns == browser_warns
