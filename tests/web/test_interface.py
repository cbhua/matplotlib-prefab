"""Compact setup, locked paper template, physical sizing and first-page preview."""
from pathlib import Path
import pytest
from conftest import needs_browser, needs_fonts
from lab import open_lab
pytestmark=[needs_browser,needs_fonts]


def test_compact_setup_and_editor():
    with open_lab() as lab:
        p=lab.page
        p.wait_for_selector('[data-venue="icml2026"]')
        assert p.locator('#setup .setup-section').count()==3
        assert p.locator('[data-venue="iclr2026"]').inner_text()=='ICLR'
        assert p.locator('[data-venue="neurips2026"]').inner_text()=='NeurIPS'
        assert p.locator('#setup-next').is_disabled()
        folder=Path('.tmp/interface');folder.mkdir(parents=True,exist_ok=True)
        p.screenshot(path=str(folder/'setup.png'),full_page=True)
        p.click('[data-venue="neurips2026"]');p.click('[data-grid="1x1"]');p.click('[data-layout="narrow"]');p.click('#setup-next')
        lab.wait_ready();lab.wait_for_render()
        assert p.locator('body > header,body > footer,#edit-setup,#paper-controls,#paper-body').count()==0
        assert p.locator('.side .card h2').first.inner_text()=='Hand off'
        assert p.locator('.side #example').count()==1
        assert p.locator('#status').is_hidden()
        assert p.locator('.reflow-paper').count()==1
        p.locator('#figure-width').fill('100');p.locator('#figure-height').fill('160');lab.wait_for_render()
        assert lab.profile()['canvas']['width_mm']==pytest.approx(100)
        assert lab.wait_for_render()['height_mm']==pytest.approx(160)
        assert p.locator('.reflow-paper').count()==1
        assert lab.export_bundle()['target']['figure_width_mm']==pytest.approx(100)
        p.locator('[data-group=type-weight] summary').click()
        weight=p.locator('#control-fonts-weight_x_label')
        weight.fill('3');weight.dispatch_event('input');lab.wait_for_render()
        assert lab.profile()['fonts']['weight_x_label']=='bold'
        assert p.locator('.weight-legend').first.inner_text().split()==['normal','medium','semibold','bold']
        p.locator('#figure-width').fill('69.85');p.locator('#figure-height').fill('43.17');lab.wait_for_render()
        p.locator('.side').evaluate('(n)=>n.scrollTop=0')
        p.screenshot(path=str(folder/'editor.png'),full_page=True,animations='disabled')
        assert not lab.page_errors


def test_compact_mobile():
    with open_lab(viewport=(390,844)) as lab:
        lab.page.wait_for_selector('[data-venue="icml2026"]')
        assert lab.page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        lab.wait_ready();lab.wait_for_render()
        assert lab.page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert lab.page.locator('.reflow-paper').count()==1
