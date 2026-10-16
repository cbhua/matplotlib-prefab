"""Permanent analysis remains beside warnings, without moving the paper/controls."""
import pytest
from pathlib import Path
from conftest import needs_browser, needs_fonts
from lab import open_lab

pytestmark = [needs_browser, needs_fonts]


@pytest.mark.parametrize('viewport', [(1024, 768), (1500, 1000), (2560, 800), (390, 844)])
def test_permanent_analysis_location_and_status_transitions(viewport):
    with open_lab(viewport=viewport) as lab:
        lab.wait_ready(); lab.wait_for_render(); p = lab.page
        assert p.locator('#analysis-panel').is_visible()
        assert p.locator('#density-readout').is_visible()
        assert p.locator('.side #figure-assessment,.side .density-card').count() == 0
        assert p.locator('#figure-assessment').get_attribute('data-state') == 'ok'
        before = p.locator('.side').bounding_box()
        lab.set_control('fonts.size_x_label_pt', 9.25); lab.wait_for_render()
        assert p.locator('#figure-assessment').get_attribute('data-state') == 'warn'
        assert p.locator('.warning-card').filter(has_text='Axis label sizes differ').is_visible()
        rail = p.locator('#warning-rail').bounding_box()
        analysis = p.locator('#analysis-panel').bounding_box()
        assert rail['width'] == pytest.approx(analysis['width'], abs=1)
        assert rail['y'] + rail['height'] <= analysis['y'] + 1
        if viewport[0] > 900:
            workspace = p.locator('.layout').bounding_box()
            assert analysis['x'] + analysis['width'] < workspace['x']
            assert analysis['y'] + analysis['height'] == pytest.approx(workspace['y'] + workspace['height'] - 8, abs=1)
            assert p.locator('.side').bounding_box() == before
        assert p.evaluate('document.documentElement.scrollWidth<=innerWidth')
        p.locator('.warning-action').first.click()
        assert p.locator('[data-path="fonts.size_y_label_pt"] input[type=range]').evaluate('(n)=>n===document.activeElement')
        lab.set_control('fonts.size_x_label_pt', 9); lab.wait_for_render()
        assert p.locator('#figure-assessment').get_attribute('data-state') == 'ok'
        assert p.locator('#warning-rail').is_hidden()
        assert p.locator('#analysis-panel').is_visible()
        lab.set_control('lines.data_linewidth_pt', -1)
        p.wait_for_function("document.querySelector('#figure-assessment').dataset.state==='error'")
        assert p.locator('#analysis-panel').is_visible()
        assert p.locator('#status').is_visible()
        assert 'Analysis will appear' in p.locator('#density-readout').inner_text()
        folder = Path('.tmp/analysis-panel'); folder.mkdir(parents=True, exist_ok=True)
        p.screenshot(path=str(folder/f'error-{viewport[0]}.png'))
        assert not lab.page_errors
