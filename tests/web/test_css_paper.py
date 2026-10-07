"""The default paper preview is static CSS; editing prose never renders a chart."""
from pathlib import Path
import pytest
from conftest import needs_browser, needs_fonts, needs_runtime
from lab import open_lab

pytestmark = [needs_browser, needs_runtime, needs_fonts]


def test_no_compiled_paper_assets_required():
    with open_lab() as session:
        requested = []
        session.page.on('request', lambda req: requested.append(req.url))
        session.page.route('**/conferences/**', lambda route: route.abort())
        session.page.reload()
        session.wait_ready()
        session.wait_for_render()
        for venue in ('iclr2026', 'icml2026', 'neurips2026'):
            for layout in ('narrow', 'wide'):
                session.select(venue, layout)
                session.wait_for_render()
                assert session.page.locator('[data-engine="css-paper"]').count() >= 1
        assert not any('/conferences/' in url for url in requested)
        assert not session.page_errors


@pytest.mark.parametrize('venue', ['iclr2026', 'icml2026', 'neurips2026'])
@pytest.mark.parametrize('layout', ['narrow', 'wide'])
def test_physical_geometry_and_font(lab, venue, layout):
    lab.select(venue, layout)
    result = lab.wait_for_render()
    geometry = lab.page.evaluate('''async () => {
      await document.fonts.ready;
      const paper = document.querySelector('.css-paper');
      const body = paper.querySelector('.css-paper-body');
      const slot = paper.querySelector('.mpf-slot');
      return { ratio:slot.getBoundingClientRect().width/body.getBoundingClientRect().width,
        columns:getComputedStyle(body).columnCount, overflow:paper.dataset.overflow,
        font:document.fonts.check('10pt "MPF Nimbus Roman"'),
        span:getComputedStyle(paper.querySelector('figure')).columnSpan };
    }''')
    expected = 1 if layout == 'wide' else (82.55/171.45 if venue == 'icml2026' else .5)
    assert geometry['ratio'] == pytest.approx(expected, abs=.001)
    assert geometry['columns'] == ('2' if venue == 'icml2026' else '1')
    assert geometry['font'] and geometry['overflow'] == 'false'
    assert result['width_mm'] == pytest.approx(lab.page_manifest()['figure']['width_mm'])
    if venue == 'icml2026' and layout == 'wide':
        assert geometry['ratio'] == pytest.approx(1, abs=.001)
    shots = Path('.tmp/css-paper-preview'); shots.mkdir(parents=True, exist_ok=True)
    lab.page.locator('.mpf-paper').first.screenshot(path=str(shots / f'{venue}-{layout}.png'))


def test_template_typography_is_locked(lab):
    lab.select('iclr2026', 'narrow'); lab.wait_for_render()
    before=lab.export_bundle()['paper_preview']['settings']
    assert lab.page.locator('#paper-controls,#paper-body,#paper-caption,#reset-paper').count()==0
    lab.page.locator('#figure-width').fill('90');lab.page.locator('#figure-height').fill('120');lab.wait_for_render()
    assert lab.export_bundle()['paper_preview']['settings']==before
    assert lab.page.locator('.reflow-paper').count()==1
    assert not lab.page_errors
