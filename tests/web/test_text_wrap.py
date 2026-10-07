"""Single-column narrow figures wrap real browser text at a fixed physical size."""
from pathlib import Path

import pytest
from conftest import needs_browser, needs_fonts
from lab import open_lab

pytestmark = [needs_browser, needs_fonts]


@pytest.fixture
def lab():
    # Each case starts from preset dimensions, independent of earlier size edits.
    with open_lab() as session:
        session.wait_ready();session.wait_for_render()
        yield session


@pytest.mark.parametrize('venue', ['iclr2026', 'neurips2026'])
def test_half_width_figure_has_text_alongside_and_below(lab, venue):
    lab.select(venue, 'narrow')
    result = lab.wait_for_render()
    assert result['width_mm'] == pytest.approx(69.85)
    geometry = lab.page.evaluate('''() => {
      const body = document.querySelector('.mpf-wrapped-body');
      const box = node => {
        const r = node.getBoundingClientRect();
        return {left:r.left, right:r.right, top:r.top, bottom:r.bottom, width:r.width};
      };
      const words = [];
      for (const p of body.querySelectorAll('p:not([hidden])')) {
        const walker = document.createTreeWalker(p, NodeFilter.SHOW_TEXT);
        let text;
        while (text = walker.nextNode()) for (const m of text.textContent.matchAll(/\\S+/g)) {
          const range = document.createRange();
          range.setStart(text, m.index); range.setEnd(text, m.index + m[0].length);
          words.push(box(range));
        }
      }
      return {body:box(body), figure:box(body.querySelector('figure')),
              slot:box(body.querySelector('.mpf-slot')), words};
    }''')
    body, figure, slot = (geometry[key] for key in ('body', 'figure', 'slot'))
    assert slot['width'] / body['width'] == pytest.approx(.5, abs=.001)
    assert slot['right'] == pytest.approx(body['right'], abs=.1)
    assert any(w['top'] < slot['bottom'] and w['right'] <= figure['left'] for w in geometry['words'])
    assert any(w['top'] >= figure['bottom'] and w['right'] > figure['left'] + 30 for w in geometry['words'])
    assert not any(w['left'] < figure['right'] and w['right'] > figure['left'] + .1
                   and w['top'] < figure['bottom'] and w['bottom'] > figure['top']
                   for w in geometry['words'])
    assert max(w['bottom'] for w in geometry['words']) <= body['bottom'] + 1
    bundle = lab.export_bundle()
    assert bundle['target']['float_environment'] == 'wrapfigure'
    assert '\\begin{wrapfigure}{r}{69.850mm}' in bundle['target']['insert_at']
    assert 'not LaTeX-calibrated' in bundle['target']['preview_layout']
    assert 'wrapfig' in lab.export_text()
    shots = Path('.tmp/text-wrap-preview'); shots.mkdir(parents=True, exist_ok=True)
    lab.page.locator('.mpf-paper').first.screenshot(path=str(shots / f'{venue}.png'))
    assert not lab.page_errors


@pytest.mark.parametrize('venue,layout', [
    ('iclr2026', 'wide'), ('neurips2026', 'wide'), ('icml2026', 'narrow'), ('icml2026', 'wide'),
])
def test_other_layouts_use_css_flow(lab, venue, layout):
    lab.select(venue, layout)
    lab.wait_for_render()
    assert lab.page.locator('.mpf-wrapped-body').count() == 0
    assert lab.page.locator('.css-paper-body').count() >= 1
    assert lab.page.locator('.mpf-sheet').count() == 0
    assert lab.export_bundle()['target']['float_environment'] in ('figure', 'figure*')
    assert not lab.page.locator('#wrap-note').is_visible()
