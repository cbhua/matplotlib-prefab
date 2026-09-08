"""The tool's behaviour in a real browser, driven through its own interface.

These are about the things that make a preview trustworthy rather than merely
pretty: that a stale figure is never shown beside fresh numbers, that switching
venue keeps what you changed, that a bad spec produces a sentence instead of a
crash, and that nothing can be exported as verified until it has actually been
drawn.
"""

from __future__ import annotations

import copy
import json
import os

import pytest

from conftest import GENERATED, needs_browser, needs_fonts, needs_runtime

pytestmark = [needs_browser, needs_runtime, needs_fonts]


def spec(name):
    with open(os.path.join(GENERATED, "specs", "%s.json" % name), encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(autouse=True)
def clean(lab):
    """Every test starts from the default configuration."""
    lab.reset_all()
    lab.page.select_option("#example", "line-multi")
    lab.select("icml2026", "narrow")
    lab.wait_for_render()
    yield
    lab.reset_all()


def test_the_tool_draws_at_the_slot_width(lab):
    manifest = lab.page_manifest()
    rendered = lab.wait_for_render()
    assert rendered["width_mm"] == pytest.approx(manifest["figure"]["width_mm"], abs=1e-6)
    assert lab.status()["kind"] == "ok"
    assert not lab.page_errors


def test_switching_width_mode_moves_the_width_and_keeps_the_style(lab):
    lab.set_control("fonts.size_x_label_pt", 12.5)
    lab.set_control("lines.data_linewidth_pt", 2.4)
    lab.wait_for_render()

    lab.select("icml2026", "wide")
    lab.wait_for_render()
    profile = lab.profile()

    assert profile["fonts"]["size_x_label_pt"] == 12.5, (
        "a width-mode switch must not throw away what the user changed"
    )
    assert profile["lines"]["data_linewidth_pt"] == 2.4
    assert profile["canvas"]["width_mm"] == pytest.approx(
        lab.page_manifest()["figure"]["width_mm"], abs=1e-6
    ), "the width is the only thing the mode switch is allowed to move"


def test_switching_venue_keeps_the_style_and_re_derives_the_width(lab):
    lab.set_control("fonts.size_ytick_pt", 5.5)
    lab.wait_for_render()
    before = lab.profile()["canvas"]["width_mm"]

    lab.select("iclr2026", "narrow")
    lab.wait_for_render()
    after = lab.profile()

    assert after["fonts"]["size_ytick_pt"] == 5.5
    assert after["canvas"]["width_mm"] != before
    assert after["canvas"]["width_mm"] == pytest.approx(
        lab.page_manifest()["figure"]["width_mm"], abs=1e-6)


def test_the_wide_mode_does_not_scale_the_type_up(lab):
    """A wider slot is a wider figure, not a magnified one."""
    lab.wait_for_render()
    narrow = lab.profile()["fonts"]
    lab.select("icml2026", "wide")
    lab.wait_for_render()
    wide = lab.profile()["fonts"]
    assert narrow == wide


def test_resetting_one_control_leaves_the_others_alone(lab):
    lab.set_control("fonts.size_x_label_pt", 13.0)
    lab.set_control("fonts.size_y_label_pt", 6.0)
    lab.wait_for_render()

    lab.page.click('.control[data-path="fonts.size_x_label_pt"] .control-reset')
    lab.wait_for_render()
    profile = lab.profile()

    assert "size_x_label_pt" not in profile["fonts"], (
        "resetting an override should remove it so the shared field applies again"
    )
    assert profile["fonts"]["size_y_label_pt"] == 6.0


def test_reset_all_returns_to_the_repository_profile(lab):
    lab.set_control("fonts.size_xtick_pt", 4.5)
    lab.set_control("axes.grid_alpha", 0.95)
    lab.wait_for_render()
    lab.reset_all()
    lab.wait_for_render()
    profile = lab.profile()
    assert "size_xtick_pt" not in profile["fonts"]
    assert profile["axes"]["grid_alpha"] == 0.3
    # The width still belongs to the page, not to the repository default.
    assert profile["canvas"]["width_mm"] == pytest.approx(
        lab.page_manifest()["figure"]["width_mm"], abs=1e-6)


def test_an_invalid_spec_comes_back_as_a_message(lab):
    broken = spec("line-multi")
    broken["series"] = [{"name": "a", "y": [1.0, 2.0]}]
    reply = lab.render_once(broken, lab.profile())
    assert reply["result"]["ok"] is False
    assert "same length as x" in reply["result"]["error"], reply["result"]["error"]
    assert reply["result"]["error_kind"] == "SpecError"
    # And the worker is still alive afterwards.
    good = lab.render_once(spec("line-multi"), lab.profile())
    assert good["result"]["ok"] is True


def test_an_invalid_profile_comes_back_as_a_message(lab):
    profile = lab.profile()
    profile["fonts"]["size_tick_pt"] = -3
    reply = lab.render_once(spec("line-multi"), profile)
    assert reply["result"]["ok"] is False
    assert "strictly positive" in reply["result"]["error"]


def test_a_superseded_result_never_replaces_a_newer_one(lab):
    """Move several controls in quick succession; the figure must end up matching
    the last one, not whichever render happened to finish last."""
    for value in (5.0, 9.0, 14.0, 6.5):
        lab.set_control("fonts.size_x_label_pt", value)
    rendered = lab.wait_for_render()
    assert lab.profile()["fonts"]["size_x_label_pt"] == 6.5
    assert rendered["resolved_profile"]["fonts"]["size_x_label_pt"] == 6.5, (
        "the figure on screen belongs to a configuration the user has moved past"
    )
    assert rendered["signature"] == lab.page.evaluate("window.__labApi.signature()")


def test_the_preview_is_marked_stale_while_a_render_is_pending(lab):
    lab.page.evaluate("() => window.__labApi.setControl('fonts.size_x_label_pt', 15)")
    # Immediately after a change, before the debounce has even fired.
    classes = lab.page.get_attribute("#preview", "class")
    assert "is-stale" in classes, (
        "the sheet must be visibly out of date the moment a control moves"
    )
    lab.wait_for_render()
    assert "is-stale" not in lab.page.get_attribute("#preview", "class")


def test_export_is_refused_until_the_configuration_has_been_drawn(lab):
    lab.page.evaluate("() => window.__labApi.setControl('fonts.size_y_label_pt', 11)")
    assert not lab.export_ready(), (
        "a configuration that has not rendered must not be exportable as verified"
    )
    assert lab.page.get_attribute("#copy-handoff", "disabled") is not None
    lab.wait_for_render()
    assert lab.export_ready()
    assert lab.page.get_attribute("#copy-handoff", "disabled") is None


def test_the_clipboard_failing_shows_the_text_instead(lab):
    lab.wait_for_render()
    lab.page.evaluate(
        "() => { Object.defineProperty(navigator, 'clipboard', "
        "{ configurable: true, get: () => undefined }); }"
    )
    lab.page.click("#copy-handoff")
    lab.page.wait_for_selector("#copy-fallback:not([hidden])", timeout=10_000)
    text = lab.page.input_value("#copy-fallback textarea")
    assert "render.py" in text and "profile.json" in text
    assert lab.status()["kind"] == "warn"
    lab.page.reload()
    lab.wait_ready()
    lab.wait_for_render()


def test_the_venue_tabs_are_keyboard_operable(lab):
    tabs = lab.page.query_selector_all("#venue-tabs .tab")
    assert len(tabs) == 3
    selected = [tab for tab in tabs if tab.get_attribute("aria-selected") == "true"]
    assert len(selected) == 1
    selected[0].focus()
    lab.page.keyboard.press("ArrowRight")
    lab.wait_for_render()
    now = [tab.get_attribute("aria-selected") for tab in lab.page.query_selector_all("#venue-tabs .tab")]
    assert now.count("true") == 1
    assert lab.page.evaluate("document.activeElement.getAttribute('aria-selected')") == "true"


def test_bar_only_controls_are_disabled_for_a_line_chart(lab):
    row = lab.page.query_selector('.control[data-path="bar.width_fraction"]')
    assert "is-inapplicable" in row.get_attribute("class")
    assert lab.page.query_selector('.control[data-path="bar.width_fraction"] input[type=number]') \
        .get_attribute("disabled") is not None
    lab.page.select_option("#example", "bar-signed")
    lab.wait_for_render()
    row = lab.page.query_selector('.control[data-path="bar.width_fraction"]')
    assert "is-inapplicable" not in row.get_attribute("class")


def test_title_controls_say_why_they_are_disabled(lab):
    row = lab.page.query_selector('.control[data-path="fonts.size_title_pt"]')
    assert "is-inapplicable" in row.get_attribute("class")
    reason = lab.page.inner_text('.control[data-path="fonts.size_title_pt"] .control-reason')
    assert "no title" in reason


def test_the_number_box_accepts_a_value_outside_the_slider_range(lab):
    """The slider's range is convenience; the validator decides what is legal."""
    box = lab.page.query_selector('.control[data-path="fonts.size_x_label_pt"] input[type=number]')
    assert box.get_attribute("min") is None and box.get_attribute("max") is None
    box.fill("24")
    box.dispatch_event("change")
    rendered = lab.wait_for_render()
    assert rendered["resolved_profile"]["fonts"]["size_x_label_pt"] == 24


def test_many_renders_do_not_grow_the_worker_without_bound(lab):
    """Figures are closed and proxies released; a long session must stay flat."""
    profile = lab.profile()
    lab.render_once(spec("line-multi"), profile)
    before = lab.javascript_heap_bytes()
    for index in range(40):
        edited = copy.deepcopy(profile)
        edited["fonts"]["size_axis_label_pt"] = 7.0 + (index % 8) * 0.5
        reply = lab.render_once(spec("line-multi"), edited)
        assert reply["result"]["ok"]
    after = lab.javascript_heap_bytes()
    if before is None or after is None:
        pytest.skip("this browser does not expose performance.memory")
    growth = after - before
    assert growth < 64 * 1024 * 1024, (
        "the JavaScript heap grew by %.1f MiB over 40 renders, which suggests each render "
        "is leaving something behind" % (growth / (1024 * 1024))
    )


def test_a_crowded_figure_is_reported_rather_than_just_drawn(lab):
    """The plan's requirement: crowding warns; the slot never grows to hide it."""
    lab.select("neurips2026", "narrow")
    lab.page.select_option("#example", "bar-signed")
    lab.wait_for_render()

    before = lab.page_manifest()["slot"]["width_mm"]
    assert lab.status()["kind"] == "warn", lab.status()
    checks = lab.page.inner_text("#checks")
    assert "tick_label_overlap" in checks, checks

    # And the slot is exactly where it was: the tool reports the problem instead
    # of quietly making room for it.
    assert lab.page_manifest()["slot"]["width_mm"] == before
    rendered = lab.wait_for_render()
    assert rendered["width_mm"] == pytest.approx(before, abs=0.01)


def test_pushing_the_type_up_starts_warning(lab):
    lab.select("iclr2026", "narrow")
    lab.wait_for_render()
    assert lab.status()["kind"] == "ok", "the default should be clean at this width"

    lab.set_control("fonts.size_x_label_pt", 20)
    lab.set_control("fonts.size_y_label_pt", 20)
    lab.set_control("fonts.size_xtick_pt", 16)
    lab.wait_for_render()
    assert lab.status()["kind"] == "warn", (
        "type this large in a 69.85 mm slot has to produce a warning, not a silent "
        "crowded figure"
    )
    assert lab.page.inner_text("#checks").strip()


def test_a_clean_figure_says_so_without_claiming_a_visual_review(lab):
    lab.select("icml2026", "wide")
    lab.wait_for_render()
    assert lab.status()["kind"] == "ok"
    note = lab.page.inner_text("#checks")
    assert "not a visual review" in note.lower() or "visual review" in note.lower()


def test_the_checks_travel_with_the_export(lab):
    lab.select("neurips2026", "narrow")
    lab.page.select_option("#example", "bar-signed")
    lab.wait_for_render()
    text = lab.export_text()
    assert "Checks at this size" in text
    assert "tick_label_overlap" in text
    assert "visual_review is open" in text
    assert "do not silently change values" in text
    bundle = lab.export_bundle()
    assert bundle["render"]["checks"]["status"] in ("pass", "warn")


def test_the_check_list_is_hidden_while_a_render_is_pending(lab):
    lab.wait_for_render()
    lab.page.evaluate("() => window.__labApi.setControl('fonts.size_xtick_pt', 12)")
    assert lab.page.get_attribute("#checks", "hidden") is not None, (
        "a check list describing the previous figure must not sit under a new one"
    )
    lab.wait_for_render()


def test_no_page_errors_were_raised_during_the_session(lab):
    assert not lab.page_errors, lab.page_errors[:5]
