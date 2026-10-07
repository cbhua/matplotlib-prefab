"""Independent browser SVG renderer: real geometry, offline operation and controls."""
from pathlib import Path
import json, re, hashlib
import xml.etree.ElementTree as ET
import pytest
from conftest import needs_browser, REPO_ROOT
from lab import browser_runtime
from server import static_server

pytestmark=[needs_browser]
ROOT=Path(REPO_ROOT)

@pytest.fixture(scope='module')
def demo():
    with static_server(str(ROOT/'web')) as origin, browser_runtime() as runtime:
        browser=runtime.chromium.launch()
        page=browser.new_page(viewport={'width':1500,'height':1050})
        errors=[]; requests=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('request',lambda request:requests.append(request.url))
        page.route('**/api/**',lambda route:route.abort())
        page.route('**/pyodide/**',lambda route:route.abort())
        page.goto(origin+'/chart-demo.html')
        page.wait_for_function('window.__ready || window.__chartDemoError')
        assert page.evaluate('window.__chartDemoError || null') is None
        idle(page)
        yield page,requests
        assert not errors
        assert not any('/api/' in u or '/pyodide/' in u for u in requests)
        browser.close()

def idle(page):
    page.wait_for_function('window.__chartDemo && !window.__chartDemo.busy')
    assert not page.locator('#error').is_visible(),page.locator('#error').text_content()

CASES=json.loads((ROOT/'web/chart-demo/references.json').read_text())['cases']

@pytest.mark.parametrize('case',CASES,ids=lambda c:c['id'])
def test_same_data_physical_units_and_reference(demo,case):
    page,_=demo
    page.select_option('#case',case['id']);idle(page)
    assert page.evaluate('window.__chartDemo.matched')
    got=page.evaluate('''() => ({geometry:window.__chartDemo.geometry,
      rect:{width:document.querySelector('#native svg').getBoundingClientRect().width,height:document.querySelector('#native svg').getBoundingClientRect().height},
      paths:[...document.querySelectorAll('.data-line')].map(n=>({d:n.getAttribute('d'),width:Number(n.getAttribute('stroke-width')),color:n.getAttribute('stroke')})),
      bars:[...document.querySelectorAll('.data-bar')].map(n=>Object.fromEntries(['x','y','width','height'].map(k=>[k,Number(n.getAttribute(k))]))),
      text:[...document.querySelectorAll('#native [data-chart-text]')].map(n=>n.textContent)})''')
    g=got['geometry'];p=case['profile'];spec=case['spec']
    assert got['rect']['width']*25.4/96==pytest.approx(p['canvas']['width_mm'],abs=.02)
    assert got['rect']['height']*25.4/96==pytest.approx(p['canvas']['width_mm']*p['canvas']['aspect_ratio'],abs=.02)
    assert spec['x_label'] in got['text'] and spec['y_label'] in got['text']
    # Independent oracle: the axes rectangle in the frozen Matplotlib SVG.
    tree=ET.parse(ROOT/'web/chart-demo'/case['asset'])
    path=next(n for n in tree.iter() if n.get('id')=='patch_2')[0].get('d')
    edges=list(map(float,re.findall(r'-?\d+(?:\.\d+)?',path)))
    for key,value in dict(left=edges[0],bottom=edges[1],right=edges[2],top=edges[5]).items():
        assert abs(g[key]-value)*25.4/72 < .03
    if spec['kind']=='line':
        assert len(got['paths'])==len(spec['series'])
        for i,path in enumerate(got['paths']):
            values=[float(v) for v in re.findall(r'-?\d+(?:\.\d+)?(?:e[+-]?\d+)?',path['d'])]
            points=list(zip(values[::2],values[1::2]));assert len(points)==len(spec['x'])
            for j,(x,y) in enumerate(points):
                rx=g['xDomain'][0]+(x-g['left'])/(g['right']-g['left'])*(g['xDomain'][1]-g['xDomain'][0])
                ry=g['yDomain'][0]+(g['bottom']-y)/(g['bottom']-g['top'])*(g['yDomain'][1]-g['yDomain'][0])
                assert rx==pytest.approx(spec['x'][j],abs=1e-8)
                assert ry==pytest.approx(spec['series'][i]['y'][j],abs=1e-8)
            assert path['width']==p['lines']['data_linewidth_pt']
            assert path['color']==p['colors']['categorical'][i]
    else:
        zero=g['bottom']-(0-g['yDomain'][0])/(g['yDomain'][1]-g['yDomain'][0])*(g['bottom']-g['top'])
        assert len(got['bars'])==len(spec['values'])
        for b,value in zip(got['bars'],spec['values']):
            assert b['height']/(g['bottom']-g['top'])*(g['yDomain'][1]-g['yDomain'][0])==pytest.approx(abs(value))
            assert (b['y']+b['height'] if value>0 else b['y'])==pytest.approx(zero)
    folder=ROOT/'.tmp/native-chart';folder.mkdir(parents=True,exist_ok=True)
    page.locator('#stage').screenshot(path=str(folder/f"{case['id']}.png"))
    assert hashlib.sha256((ROOT/'web/chart-demo'/case['asset']).read_bytes()).hexdigest()==case['sha256']


def test_resize_without_network_and_export(demo):
    page,requests=demo;page.select_option('#case','line-default');idle(page)
    count=len(requests)
    before=page.locator('.data-line').first.get_attribute('d')
    page.locator('#height').fill('100');idle(page)
    assert page.locator('.data-line').first.get_attribute('d')!=before
    assert page.locator('.xlabel').get_attribute('font-size')=='9'
    assert page.locator('.data-line').first.get_attribute('stroke-width')=='1.2'
    assert not page.evaluate('window.__chartDemo.matched')
    assert page.locator('#view option[value=overlay]').evaluate('(n)=>n.disabled')
    page.locator('#type').fill('10');idle(page)
    assert page.locator('.xlabel').get_attribute('font-size')=='11'
    page.locator('#line-width').fill('2');idle(page)
    assert page.locator('.data-line').first.get_attribute('stroke-width')=='2'
    page.locator('#markers').uncheck();idle(page)
    assert page.locator('.data-marker').count()==0
    assert len(requests)==count
    with page.expect_download() as event:page.click('#download')
    svg=Path(event.value.path()).read_text()
    assert 'data-chart-text=' in svg
    assert '<text' not in svg  # outline export needs no external font
    assert '<image' not in svg and '<script' not in svg
    assert float(re.search(r'height="([0-9.]+)mm"',svg)[1]) == pytest.approx(100)
    page.click('#reset');idle(page);assert page.evaluate('window.__chartDemo.matched')


def test_invalid_size_retains_last_valid_chart(demo):
    page,_=demo
    before=page.locator('#native').inner_html()
    page.locator('#height').fill('0')
    page.wait_for_function('!window.__chartDemo.busy')
    assert page.locator('#error').is_visible() and page.locator('#download').is_disabled()
    assert page.locator('#native').inner_html()==before
    page.click('#reset');idle(page)


def test_text_modes_and_portable_browser_export(demo):
    page,requests=demo
    page.select_option('#case','line-default');idle(page)
    count=len(requests)
    assert page.locator('#native text').count()==0
    page.select_option('#text-mode','browser');idle(page)
    assert page.locator('#native text').count()>0
    assert page.evaluate('window.__chartDemo.matched')
    with page.expect_download() as event:page.click('#download')
    svg=Path(event.value.path()).read_text()
    assert '<text' in svg and 'data:font/woff2;base64,' in svg
    page.select_option('#text-mode','outlines');idle(page)
    assert page.locator('#native text').count()==0
    assert len(requests)==count


def test_reference_modes_rotation_and_invalid_overlap(demo):
    page,_=demo
    page.select_option('#case','bar-default');idle(page)
    page.select_option('#view','overlay')
    assert 'overlay' in page.locator('#stage').get_attribute('class')
    page.select_option('#view','difference')
    assert 'difference' in page.locator('#stage').get_attribute('class')
    page.select_option('#rotation','45');idle(page)
    assert page.locator('.xtick').first.get_attribute('transform').startswith('rotate(-45')
    assert page.locator('#view').input_value()=='side'
    page.select_option('#rotation','0');page.locator('#width').fill('60');page.locator('#type').fill('14');idle(page)
    assert 'overlap' in page.locator('#warnings').text_content()
    page.click('#reset');idle(page)
