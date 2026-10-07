"""Variable-height figures must move real text without dropping it or scaling it."""
from pathlib import Path
import pytest
from conftest import needs_browser, needs_fonts, REPO_ROOT
from lab import browser_runtime
from server import static_server

pytestmark = [needs_browser, needs_fonts]


@pytest.fixture(scope='module')
def flow():
    with static_server(str(Path(REPO_ROOT) / 'web')) as origin, browser_runtime() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={'width': 1500, 'height': 1200})
        errors = []; page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(origin + '/reflow.html')
        page.wait_for_function('window.__ready || window.__reflowError')
        assert page.evaluate('window.__reflowError || null') is None
        yield page
        assert not errors
        browser.close()


def idle(page):
    page.wait_for_function('window.__reflow && !window.__reflow.busy')
    assert not page.locator('#error').is_visible(), page.locator('#error').text_content()


def verify_content(page):
    result = page.evaluate('''() => {
      const blocks = window.__reflow.blocks;
      const fragments = [...document.querySelectorAll('#pages .flow-fragment')];
      const content = blocks.every(b => {
        const f = fragments.filter(n => Number(n.dataset.block) === b.index);
        const text = f.map(n => n.textContent).join(' ');
        const expected = b.tokens.map(w => w.map(s => s.text).join('')).join(' ');
        return text === expected && Number(f[0]?.dataset.start) === 0
          && Number(f.at(-1)?.dataset.end) === b.tokens.length
          && f.every((n, i) => !i || n.dataset.start === f[i-1].dataset.end);
      });
      const bounds = fragments.every(n => {
        const r = n.getBoundingClientRect(), c = n.parentElement.getBoundingClientRect();
        return r.top >= c.top - 1 && r.bottom <= c.bottom + 1 && r.left >= c.left - 1 && r.right <= c.right + 1;
      });
      const figure = document.querySelector('.reflow-figure').getBoundingClientRect();
      const noOverlap = fragments.every(n => { const r = n.getBoundingClientRect();
        return r.right <= figure.left || r.left >= figure.right || r.top >= figure.bottom || r.bottom <= figure.top; });
      const slot = document.querySelector('.reflow-slot').getBoundingClientRect();
      return {content, bounds, noOverlap, height:slot.height * 25.4/96,
        width:slot.width * 25.4/96, pages:window.__reflow.result.pages,
        font:getComputedStyle(fragments.find(n => n.tagName === 'P')).fontSize,
        time:window.__reflow.result.durationMs};
    }''')
    assert result['content'], 'Text missing, duplicated or out of order'
    assert result['bounds'], 'Text outside its page column'
    assert result['noOverlap'], 'Text overlaps figure/caption'
    return result


@pytest.mark.parametrize('width', ['narrow', 'wide'])
def test_height_changes_paginate_and_return(flow, width):
    flow.select_option('#width', width)
    states = []
    for height in [20, 80, 160, 20]:
        flow.locator('#height').fill(str(height)); idle(flow)
        result = verify_content(flow)
        assert result['height'] == pytest.approx(height, abs=.02)
        assert result['width'] == pytest.approx(82.55 if width == 'narrow' else 171.45, abs=.02)
        states.append(result)
        folder = Path('.tmp/reflow'); folder.mkdir(parents=True, exist_ok=True)
        flow.locator('.reflow-paper').first.screenshot(path=str(folder / f'{width}-{height}.png'))
    assert states[-1]['pages'] == states[0]['pages']
    assert states[2]['pages'] >= states[0]['pages']
    assert len({s['font'] for s in states}) == 1
    assert states[2]['pages'] >= 2


def test_arbitrary_text_and_caption(flow):
    flow.locator('summary').filter(has_text='Body text').click()
    flow.locator('#body').fill('## New heading\n\n' + ('Modified body with a long paragraph. ' * 140) + '\n\nFinal body paragraph.')
    flow.locator('#caption').fill('Figure 1. ' + 'Longer caption moves the following text. ' * 8)
    idle(flow); verify_content(flow)
    assert flow.locator('.flow-fragment').filter(has_text='Final body paragraph.').count() == 1
    flow.click('#reset'); idle(flow); verify_content(flow)


def test_invalid_height_and_caption_retain_valid_page(flow):
    previous = flow.locator('#pages').inner_html()
    flow.locator('#height').fill('999')
    flow.wait_for_function('!window.__reflow.busy')
    assert flow.locator('#error').is_visible()
    assert flow.locator('#pages').inner_html() == previous
    flow.locator('#height').fill('180'); idle(flow)
    previous = flow.locator('#pages').inner_html()
    flow.locator('#caption').fill('Very long caption. ' * 300)
    flow.wait_for_function('!window.__reflow.busy')
    assert flow.locator('#error').is_visible()
    assert flow.locator('#pages').inner_html() == previous
    flow.click('#reset'); idle(flow)


def test_upload_and_slider(flow):
    flow.locator('#image').set_input_files(str(Path(REPO_ROOT) / 'web/reference/icml2026-narrow.png'))
    flow.wait_for_selector('.reflow-slot img')
    flow.locator('#height-slider').evaluate("n => { n.value='100'; n.dispatchEvent(new Event('input', {bubbles:true})); }")
    idle(flow)
    assert verify_content(flow)['height'] == pytest.approx(100, abs=.02)
    assert flow.locator('.reflow-slot img').evaluate('n => n.complete && n.naturalWidth > 0')
    flow.click('#remove-image'); idle(flow)
    assert flow.locator('.reflow-slot img').count() == 0


def test_rapid_resizing_uses_latest_value_without_network(flow):
    requests = []
    listener = lambda request: requests.append(request.url)
    flow.on('request', listener)
    try:
        flow.locator('#height-slider').evaluate('''n => {
          for (const height of [25, 80, 140, 35]) {
            n.value = height; n.dispatchEvent(new Event('input', {bubbles:true}));
          }
        }''')
        idle(flow)
        assert verify_content(flow)['height'] == pytest.approx(35, abs=.02)
        assert not requests
    finally:
        flow.remove_listener('request', listener)
