"""The six calibrated pages say what the templates measured, and were checked.

These assert on committed evidence rather than recompiling LaTeX: the generator
is slow and needs a toolchain, and the point of committing its output is that a
reviewer — and this suite — can see what it found.
"""

from __future__ import annotations

import json
import os

import pytest

from conftest import GENERATED, REPO_ROOT, load_report

CONFERENCES = os.path.join(GENERATED, "conferences")

# The widths the venue templates give a figure, as measured by TeX in the
# document. They are repeated here on purpose: if a template changes, or the
# evaluator starts computing a width differently, this is where it shows.
EXPECTED_WIDTH_MM = {
    ("iclr2026", "narrow"): 69.85,
    ("iclr2026", "wide"): 139.70,
    ("neurips2026", "narrow"): 69.85,
    ("neurips2026", "wide"): 139.70,
    ("icml2026", "narrow"): 82.55,
    ("icml2026", "wide"): 171.45,
}

PAIRS = sorted(EXPECTED_WIDTH_MM)


def page(venue, layout):
    path = os.path.join(CONFERENCES, venue, layout, "page.json")
    if not os.path.isfile(path):
        pytest.skip("%s has not been generated; run "
                    "`python scripts/calibrate_conference_pages.py --generate`" % path)
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def test_the_index_lists_exactly_the_matrix():
    path = os.path.join(CONFERENCES, "index.json")
    if not os.path.isfile(path):
        pytest.skip("run `python scripts/calibrate_conference_pages.py --generate`")
    with open(path, encoding="utf-8") as handle:
        index = json.load(handle)
    listed = sorted((entry["venue"], entry["layout"]) for entry in index["pages"])
    assert listed == PAIRS


@pytest.mark.parametrize("venue,layout", PAIRS)
def test_the_slot_is_the_width_the_template_gives_a_figure(venue, layout):
    manifest = page(venue, layout)
    expected = EXPECTED_WIDTH_MM[(venue, layout)]
    # 0.01 mm: the slot is measured off the compiled PDF, whose numbers are
    # rounded to a few decimal places of a point.
    assert manifest["slot"]["width_mm"] == pytest.approx(expected, abs=0.01)
    assert manifest["figure"]["width_mm"] == pytest.approx(expected, abs=0.01)
    assert manifest["slot"]["width_mm"] == pytest.approx(manifest["figure"]["width_mm"], abs=0.01)


@pytest.mark.parametrize("venue,layout", PAIRS)
def test_the_page_is_us_letter_and_carries_real_prose(venue, layout):
    manifest = page(venue, layout)
    assert manifest["paper"]["width_mm"] == pytest.approx(215.9, abs=0.01)
    assert manifest["paper"]["height_mm"] == pytest.approx(279.4, abs=0.01)
    body = [run for run in manifest["runs"] if run.get("region") == "body"]
    assert len(body) > 150, "a body page with almost no text is not body-page context"


@pytest.mark.parametrize("venue,layout", PAIRS)
def test_every_run_is_either_a_packaged_face_or_an_outline(venue, layout):
    manifest = page(venue, layout)
    for run in manifest["runs"]:
        if run["mode"] == "text":
            assert run["css_family"], "a text run must name the face it is set in"
            assert run["weight"] in ("normal", "bold")
        else:
            assert run["glyphs"], "an outline run must carry its glyphs"
            for glyph in run["glyphs"]:
                assert glyph["key"] in manifest["outline_glyphs"], (
                    "%s has no outline, so the page could not draw it" % glyph["key"]
                )


@pytest.mark.parametrize("venue,layout", PAIRS)
def test_the_two_column_venue_really_has_two_columns(venue, layout):
    manifest = page(venue, layout)
    columns = {run.get("column") for run in manifest["runs"] if run.get("region") == "body"}
    if manifest["venue"]["columns"] == 2:
        assert columns == {0, 1}, "ICML's body page must use both columns"
    else:
        assert columns == {0}, "a one-column template must not grow a second column"


def test_icml_wide_uses_the_templates_own_cross_column_float():
    manifest = page("icml2026", "wide")
    assert manifest["layout"]["float_environment"] == "figure*", (
        "the cross-column mode has to be a real figure*, not a narrow figure stretched"
    )
    assert manifest["slot"]["width_mm"] > manifest["template"]["columnwidth_mm"] * 1.9


def test_wide_modes_do_not_change_the_type_size():
    """A wider figure is a wider figure, not a bigger one."""
    for venue in ("iclr2026", "neurips2026", "icml2026"):
        narrow = page(venue, "narrow")
        wide = page(venue, "wide")
        assert narrow["figure"]["aspect_ratio"] == wide["figure"]["aspect_ratio"]
        assert wide["slot"]["width_mm"] > narrow["slot"]["width_mm"]


@pytest.mark.parametrize("venue,layout", PAIRS)
def test_the_page_records_where_it_came_from(venue, layout):
    manifest = page(venue, layout)
    provenance = manifest["provenance"]
    for key in ("baseline_pdf", "baseline_pdf_sha256", "wrapper_sha256", "body_sha256",
                "measure_sha256", "venue_files"):
        assert provenance.get(key), "the page manifest must record %s" % key
    assert os.path.isfile(os.path.join(REPO_ROOT, provenance["baseline_pdf"])), (
        "the PDF this page was measured from must be kept beside it"
    )


def test_every_calibrated_page_passed_its_comparison():
    summary = load_report("page-calibration.json")
    checked = {(entry["venue"], entry["layout"]) for entry in summary["pages"]}
    assert checked == set(PAIRS), "every venue and width mode must be compared"
    for entry in summary["pages"]:
        assert entry["status"] == "pass", (
            "%s/%s did not match the compiled page: baseline %s mm, left %s mm, width %s mm"
            % (entry["venue"], entry["layout"], entry["worst_baseline_mm"],
               entry["worst_left_edge_mm"], entry["worst_width_mm"])
        )


def test_the_calibration_thresholds_were_not_loosened():
    """The thresholds are part of the claim; a passing run against relaxed ones is not."""
    summary = load_report("page-calibration.json")
    assert summary["thresholds_mm"]["run_baseline_mm"] <= 0.2
    assert summary["thresholds_mm"]["run_left_edge_mm"] <= 0.2
    assert summary["thresholds_mm"]["slot_edge_mm"] <= 0.2
    assert summary["thresholds_mm"]["paper_size_mm"] <= 0.2
