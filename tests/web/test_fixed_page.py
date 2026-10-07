"""A live fixed-content HTML regression against the original LaTeX PDF/raster.

These tests do not require Pyodide, LaTeX, or Poppler. The historical 150 DPI
reference image is frozen; the test never updates its own golden image.
"""
import hashlib
import io
import json
from pathlib import Path

import pytest
from PIL import Image
from conftest import needs_browser, needs_fonts, REPO_ROOT
from lab import browser_runtime
from server import static_server
from verify_fixed_page import BASE, DPI, compare_geometry, compare_ink, verify

pytestmark = [needs_browser, needs_fonts]
ROOT = Path(REPO_ROOT)


@pytest.fixture(scope='module')
def reference_page():
    with static_server(str(ROOT / 'web')) as origin, browser_runtime() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={'width': 1800, 'height': 1300}, device_scale_factor=DPI/96)
        requests, errors = [], []
        page.on('request', lambda request: requests.append(request.url))
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/pyodide/**', lambda route: route.abort())
        page.goto(origin + '/reference.html?capture=1')
        page.wait_for_function('window.__ready === true')
        yield page, requests, errors
        browser.close()


def test_frozen_reference_has_not_changed():
    assert hashlib.sha256((BASE / 'page.pdf').read_bytes()).hexdigest() == 'cbd224a6448914dbd72dd1941a5cbe8010e7fc5523fa8e8273eb5c6997e0baa5'
    assert (ROOT / 'web/reference/icml2026-narrow.png').read_bytes() == (BASE / 'page.png').read_bytes()
    # Ensure the supplement accurately represents stroked PDF paths, including
    # the running-head rule and the radical's overbar missed by the old extractor.
    from pypdf import PdfReader
    from pypdf.generic import ContentStream
    from pdf_layout import IDENTITY, mat_mul, apply
    reader = PdfReader(BASE / 'page.pdf')
    matrix, width, stack, start, end, strokes = IDENTITY[:], 1, [], None, None, []
    for args, op in ContentStream(reader.pages[0].get_contents(), reader).operations:
        if op == b'q': stack.append((matrix[:], width))
        elif op == b'Q': matrix, width = stack.pop()
        elif op == b'cm': matrix = mat_mul([float(v) for v in args], matrix)
        elif op == b'w': width = float(args[0])
        elif op == b'm': start = apply(matrix, *map(float, args))
        elif op == b'l': end = apply(matrix, *map(float, args))
        elif op == b'S':
            assert start[1] == end[1], 'fixture gained a non-horizontal path'
            strokes.append(dict(x_pt=start[0], y_pt=start[1], width_pt=end[0]-start[0], height_pt=width))
    supplement = json.loads((ROOT / 'web/reference/icml2026-narrow.json').read_text())
    assert hashlib.sha256((BASE / 'page.png').read_bytes()).hexdigest() == supplement['baseline_png_sha256']
    assert len(strokes) == len(supplement['strokes']) == 2
    for got, want in zip(supplement['strokes'], strokes):
        assert got == pytest.approx(want, abs=1e-8)


def test_fixed_page_matches_original_pdf(reference_page, tmp_path):
    page, requests, errors = reference_page
    report = verify(page, tmp_path)
    assert report['status'] == 'pass', json.dumps(report, indent=2)
    assert report['geometry']['text_runs'] == 802
    assert report['geometry']['math_runs'] == 10
    assert not errors
    assert not any('/pyodide/' in url or url.endswith('.pdf') for url in requests)
    assert page.locator('.fixed-paper img, .fixed-paper canvas, .fixed-paper object, .fixed-paper iframe').count() == 0
    assert page.locator('.fixed-paper svg:not(.fixed-math)').count() == 0
    # The baseline comparison image is not a dependency of the actual page.
    page.locator('#reference').evaluate('(node) => node.remove()')
    assert compare_geometry(page.evaluate('window.__fixedPage.measure()'))['pass']


@pytest.mark.parametrize('mutation', ['shift', 'font', 'size', 'references', 'header_rule', 'folio'])
def test_regression_detects_real_defects(reference_page, mutation):
    page, _, _ = reference_page
    page.reload(); page.wait_for_function('window.__ready === true')
    page.evaluate('''mutation => {
      const nodes = [...document.querySelectorAll('.fixed-run')];
      if (mutation === 'shift') for (const n of nodes) n.style.translate = '0 1mm';
      if (mutation === 'font') for (const n of nodes) n.style.fontFamily = 'Arial';
      if (mutation === 'size') for (const n of nodes) n.style.fontSize = '15px';
      if (mutation === 'references') for (const n of nodes)
        if (parseFloat(n.style.left) > 400 && parseFloat(n.style.top) > 160) n.style.visibility = 'hidden';
      if (mutation === 'header_rule') document.querySelector('.fixed-rule').remove();
      if (mutation === 'folio') nodes.filter(n => n.textContent === '2').at(-1).style.visibility = 'hidden';
    }''', mutation)
    geometry = compare_geometry(page.evaluate('window.__fixedPage.measure()'))
    screenshot = Image.open(io.BytesIO(page.locator('.fixed-paper').screenshot())).convert('L')
    pixels = compare_ink(Image.open(BASE / 'page.png').convert('L'), screenshot)
    assert not (geometry['pass'] and pixels['pass']), f'{mutation} was not detected'
    page.reload(); page.wait_for_function('window.__ready === true')


def test_comparison_ui(reference_page):
    page, _, errors = reference_page
    page.goto(page.url.replace('?capture=1', ''))
    page.wait_for_function('window.__ready === true')
    for mode in ['baseline', 'side', 'overlay', 'difference', 'browser']:
        page.select_option('#mode', mode)
        assert page.locator('#comparison').get_attribute('data-mode') == mode
    page.click('#blink')
    assert page.locator('#comparison').get_attribute('data-mode') == 'baseline'
    assert not errors
