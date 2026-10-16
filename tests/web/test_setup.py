"""Single-screen configuration and per-panel content selection in the editor."""
from pathlib import Path
import pytest
from conftest import needs_browser,needs_fonts
from lab import open_lab
pytestmark=[needs_browser,needs_fonts]


def test_setup_defers_renderer_and_renders_mixed_grid():
    with open_lab() as lab:
        p=lab.page;p.wait_for_selector('[data-venue="icml2026"]')
        assert p.evaluate('window.__lab.worker') is None
        p.locator('[data-venue="icml2026"]').focus();p.keyboard.press('Enter')
        p.click('[data-grid="2x2"]');p.click('[data-layout="wide"]');p.click('#setup-next')
        lab.wait_ready();result=lab.wait_for_render()
        assert len(result['drawn']['panels'])==4
        assert result['width_mm']==pytest.approx(171.45)
        p.select_option('#active-panel','1');p.select_option('#example','bar-positive');lab.wait_for_render()
        assert [s['kind'] for s in lab.spec()['panels']]==['line','bar','line','line']
        assert p.locator('.reflow-slot > svg svg').count()==0
        assert p.locator('.reflow-slot .figure-panel').count()==4
        assert p.locator('.reflow-paper').count()==1
        lab.set_control('fonts.size_xtick_pt',6);lab.wait_for_render()
        assert lab.export_bundle()['target']['panel_grid']=={'rows':2,'columns':2}
        assert p.locator('.buttons button').all_text_contents()==['🤖 Copy for Agents']
        assert '"kind": "grid"' in lab.export_text()
        assert not lab.page_errors


def test_default_iclr_and_warning_panel_location():
    with open_lab() as lab:
        p=lab.page;p.wait_for_selector('#setup-next')
        p.click('[data-grid="2x2"]');p.click('#setup-next')
        lab.wait_ready();lab.wait_for_render()
        assert lab.page_manifest()['preset']['id']=='iclr2026'
        lab.set_control('fonts.size_xtick_pt',4);lab.wait_for_render()
        assert 'Shared style · All 4 panels' in p.locator('.warning-location').all_text_contents()
        check=next(c for c in lab.export_bundle()['render']['checks']['checks'] if c['id']=='paper.size_xtick_pt')
        assert check['panel_indices']==[0,1,2,3]
        assert all(not text.startswith('Panel ') for text in p.locator('.warning-message').all_text_contents())
        assert not lab.page_errors


def test_home_discards_edits_and_restores_initial_setup():
    with open_lab() as lab:
        p=lab.page;p.wait_for_selector('#setup-next')
        p.click('[data-venue="icml2026"]');p.click('[data-grid="2x2"]');p.click('#setup-next')
        lab.wait_ready();lab.wait_for_render()
        lab.set_control('fonts.size_xtick_pt',4);lab.wait_for_render()
        p.locator('#zoom').fill('1.5');p.locator('#zoom').dispatch_event('input')
        p.click('#ui-language');p.click('#home-open')
        p.wait_for_selector('#setup-next')
        assert p.locator('#editor').is_hidden()
        assert p.locator('[data-venue="iclr2026"]').get_attribute('aria-pressed')=='true'
        assert p.locator('[data-grid="1x1"]').get_attribute('aria-pressed')=='true'
        assert p.locator('[data-layout="narrow"]').get_attribute('aria-pressed')=='true'
        assert p.evaluate('window.__lab.worker') is None
        assert p.locator('#ui-language').get_attribute('data-language')=='zh'
        p.click('#setup-next');lab.wait_ready();lab.wait_for_render()
        assert lab.spec()['kind']=='line'
        assert lab.profile()['fonts'].get('size_xtick_pt',lab.profile()['fonts']['size_tick_pt'])!=4
        assert p.locator('#zoom').input_value()!='1.5'
        assert not lab.page_errors
