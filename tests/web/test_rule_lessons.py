"""The website teaches the skill using real controls, data and check results."""

import re
from pathlib import Path

import pytest

from conftest import REPO_ROOT, needs_browser, needs_fonts
from lab import open_lab

pytestmark = [needs_browser, needs_fonts]


def test_every_skill_rule_and_existing_control_has_one_home(lab):
    p = lab.page
    groups = p.locator('#panel > .rule-lesson').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.group)')
    assert groups == ['type-size', 'legend', 'lines', 'axes', 'figure-size', 'space']
    assert p.locator('[data-group=type-size] [data-path="fonts.size_x_label_pt"]').count() == 1
    paths = p.locator('#panel [data-path]').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.path)')
    assert len(paths) == len(set(paths))
    expected = p.evaluate("async()=>{const {ALL_CONTROLS}=await import('./src/controls.js');return ALL_CONTROLS.map(c=>c.path)}")
    assert set(paths) == set(expected)
    covered = p.locator('[data-skill-rules]').evaluate_all('(nodes)=>nodes.flatMap(n=>n.dataset.skillRules.split(" "))')
    catalog = Path(REPO_ROOT) / 'skills/scientific-figures/references/experience-rules.md'
    rule_ids = set(re.findall(r'^\| `([^`]+)` \|', catalog.read_text(), re.M))
    assert set(covered) == rule_ids
    assert p.locator('#figure-width').count() == 1
    assert p.locator('[data-group=figure-size] #figure-width').count() == 1
    assert p.locator('[data-group=type-size] [data-group=type-weight]').count() == 1


@pytest.mark.parametrize('experiment,restore,group,warning', [
    ('oversized-type', 'restore-type', 'type-size', 'paper.size_x_label_pt'),
    ('hairlines', 'restore-strokes', 'lines', 'panel_1.thin_strokes'),
    ('large-legend', 'restore-legend', 'legend', 'panel_1.legend_data_overlap'),
    ('crowded-ticks', 'restore-labels', 'axes', 'panel_1.tick_label_overlap'),
])
def test_experiments_trigger_real_checks_and_restore_without_changing_data(experiment, restore, group, warning):
    with open_lab() as lab:
        p = lab.page
        p.wait_for_selector('#setup-next');p.click('[data-venue=iclr2026]');p.click('#setup-next')
        lab.wait_ready();lab.wait_for_render()
        original = lab.export_bundle()
        p.click(f'[data-experiment="{experiment}"]');lab.wait_for_render()
        checks = lab.export_bundle()['render']['checks']['checks']
        assert any(c['id'] == warning for c in checks), checks
        assert p.locator(f'[data-group={group}]').get_attribute('data-check-state') == 'warn'
        assert lab.spec() == original['spec']
        changed = lab.profile()
        # One experiment is one undo step, despite editing multiple fields.
        p.click('#undo-style');lab.wait_for_render()
        assert lab.profile() == original['profile']
        p.click(f'[data-experiment="{experiment}"]');lab.wait_for_render()
        p.click(f'[data-experiment="{restore}"]');lab.wait_for_render()
        assert not any(c['id'] == warning for c in lab.export_bundle()['render']['checks']['checks'])
        assert lab.spec() == original['spec'] and lab.profile() != changed
        assert not lab.page_errors


def test_lesson_feedback_tracks_manual_edits_and_invalid_configuration():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render();p=lab.page
        lab.set_control('fonts.size_xtick_pt',4);lab.wait_for_render()
        assert p.locator('[data-group=type-size]').get_attribute('data-check-state') == 'warn'
        assert 'X tick labels' in p.locator('[data-group=type-size] > .lesson-feedback').inner_text()
        lab.set_control('fonts.size_xtick_pt',8);lab.wait_for_render()
        assert p.locator('[data-group=type-size]').get_attribute('data-check-state') == 'clear'
        lab.set_control('fonts.size_x_label_pt',-1)
        p.wait_for_function("document.querySelector('#status').dataset.kind==='error'")
        assert p.locator('.rule-lesson[data-check-state=clear]').count() == 0
        assert p.locator('.rule-lesson[data-check-state=error]').count() == 6


def test_bar_specific_controls_and_nonwrapped_reference_are_truthful():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render();p=lab.page
        original = lab.spec()
        p.click('[data-experiment=large-marks]');lab.wait_for_render()
        assert lab.profile()['lines']['marker_size_pt'] == 10
        assert lab.spec() == original
        p.select_option('#example','bar-signed');lab.wait_for_render()
        assert p.locator('[data-group=legend]').is_hidden()
        assert p.locator('[data-group=space] [data-path="bar.width_fraction"]').is_visible()
        assert p.locator('[data-group=axes] [data-path="bar.category_label_rotation_deg"]').is_visible()
        assert p.locator('[data-experiment=large-marks]').is_hidden()
        assert p.locator('[data-path="lines.marker_size_pt"]').is_hidden()
        assert 'zero values retained' in p.locator('#integrity-readout').inner_text()
        # The lab default is ICML's non-wrapped column layout.
        assert 'does not apply' in p.locator('[data-group=figure-size] > .lesson-reference').inner_text()
        p.select_option('#example','line-single');lab.wait_for_render()
        assert p.locator('[data-path="fonts.size_legend_pt"]').is_hidden()
        p.locator('#control-legend-placement-outside').check();lab.wait_for_render()
        assert p.locator('[data-path="fonts.size_legend_pt"]').is_visible()


def test_lessons_translate_without_affecting_the_export(lab):
    p=lab.page
    original = lab.export_bundle()
    p.click('#ui-language')
    assert p.locator('[data-group=type-size] > summary > .lesson-name').inner_text() == '字号与正文的关系'
    assert '正文' in p.locator('[data-group=type-size] > .lesson-reference').inner_text()
    assert '正文的' in p.locator('[data-group=type-size] > .lesson-reading').inner_text()
    assert p.locator('[data-experiment=oversized-type]').inner_text() == '试试放大轴标题'
    assert lab.export_bundle()['spec'] == original['spec']
    assert lab.export_bundle()['profile'] == original['profile']
    p.click('#ui-language')
    assert p.locator('[data-experiment=oversized-type]').inner_text() == 'Try oversized labels'
