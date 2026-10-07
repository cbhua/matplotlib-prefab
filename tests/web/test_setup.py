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
