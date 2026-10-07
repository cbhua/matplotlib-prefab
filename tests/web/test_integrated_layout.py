"""The main tool combines server-rendered figures and pure browser pagination."""
import json
from pathlib import Path
import pytest
from conftest import needs_browser, needs_fonts, REPO_ROOT
from lab import Lab, browser_runtime
from server import static_server

pytestmark = [needs_browser, needs_fonts]


@pytest.fixture(scope='module')
def integrated():
    with static_server(str(Path(REPO_ROOT) / 'web'), renderer=True) as origin, browser_runtime() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={'width': 1500, 'height': 1100})
        session = Lab(page, origin, browser.version)
        errors, requests = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda req: requests.append(req.url))
        page.route('**/pyodide/**', lambda route: route.abort())
        page.goto(origin + '/index.html')
        session.wait_ready(); session.wait_for_render()
        yield session
        assert not errors
        assert not any('/pyodide/' in url or '/api/' in url for url in requests)
        browser.close()


@pytest.mark.parametrize('venue', ['icml2026', 'neurips2026', 'iclr2026'])
@pytest.mark.parametrize('layout', ['narrow', 'wide'])
def test_all_presets_height_reflow_and_export(integrated, venue, layout):
    session = integrated
    session.select(venue, layout); session.wait_for_render()
    for height in [40, 140, 40]:
        session.page.locator('#figure-height').fill(str(height))
        session.wait_for_render()
        result = session.page.evaluate('''() => {
          const s=window.__lab, z=Number(document.querySelector('#zoom').value);
          const slot=s.slot.getBoundingClientRect();
          return {height:slot.height/z*25.4/96,width:slot.width/z*25.4/96,
            paper:s.page.figure, rendered:s.lastGood.height_mm,
            texts:[...document.querySelectorAll('#paper-scale .flow-fragment')].map(n=>({
              block:Number(n.dataset.block),start:Number(n.dataset.start),end:Number(n.dataset.end),text:n.textContent})),
            columns:s.page.venue.columns, pages:s.pageCount,
            wrap:s.page.layout.text_wrap, backend:s.assets.render_backend};
        }''')
        assert result['pages']==1
        assert result['height'] == pytest.approx(height, abs=.03)
        assert result['rendered'] == pytest.approx(height, abs=.01)
        assert result['width'] == pytest.approx(result['paper']['width_mm'], abs=.03)
        assert result['backend'] == 'svg-outlines'
        assert result['wrap'] == (venue != 'icml2026' and layout == 'narrow')
        assert result['columns'] == (2 if venue == 'icml2026' else 1)
        fragments = result['texts']
        for block in {n['block'] for n in fragments}:
            items = [n for n in fragments if n['block'] == block]
            assert items[0]['start'] == 0
            assert all(a['end'] == b['start'] for a,b in zip(items,items[1:]))
        assert not any(symbol in ''.join(n['text'] for n in fragments) for symbol in ['dₖ','dᵥ','√'])
        bundle = session.export_bundle()
        assert bundle['target']['figure_height_mm'] == pytest.approx(height)
        assert bundle['profile']['canvas']['width_mm']*bundle['profile']['canvas']['aspect_ratio'] == pytest.approx(height)
    folder = Path('.tmp/integrated-layout'); folder.mkdir(parents=True, exist_ok=True)
    session.page.locator('.reflow-paper').first.screenshot(path=str(folder / f'{venue}-{layout}.png'))


def test_backend_rejects_bad_input_and_reports_validation(integrated):
    request = integrated.page.request
    response = request.post(integrated.origin+'/api/render', data={'spec': {}, 'profile': {}})
    assert response.status == 200
    assert response.json()['ok'] is False
    response = request.post(integrated.origin+'/api/render', data={'spec': {'path':'/etc/passwd'}})
    assert response.status == 400


def test_size_edit_does_not_call_backend(integrated):
    page=integrated.page;requests=[]
    listener=lambda req:requests.append(req.url)
    page.on('request',listener)
    try:
        page.locator('#figure-height').fill('120');integrated.wait_for_render()
        assert not any('/api/' in url for url in requests)
        assert page.locator('.reflow-paper').count()==1
    finally:page.remove_listener('request',listener)


def test_backend_grid_uses_same_renderer(integrated):
    spec = integrated.spec()
    profile = integrated.profile()
    grid = {'schema_version':'1', 'kind':'grid', 'rows':1, 'columns':2, 'panels':[spec, spec]}
    response = integrated.page.request.post(integrated.origin+'/api/render', data={'spec':grid, 'profile':profile})
    result = response.json()
    assert result['ok'], result
    assert result['resolved_spec']['kind'] == 'grid'
    assert result['height_mm'] == pytest.approx(profile['canvas']['width_mm'] * profile['canvas']['aspect_ratio'])


def test_outline_controls_and_static_exports(integrated):
    page=integrated.page
    result=page.evaluate('''async()=>{
      const {renderNativeChart}=await import('./src/native-chart.js');
      const {ALL_CONTROLS,setPath,effectiveValue}=await import('./src/controls.js');
      const atlas=await fetch('./chart-demo/text-outlines.json').then(r=>r.json());
      const profile=await fetch('./public/generated/profiles/single-column.json').then(r=>r.json());
      const line=await fetch('./public/generated/specs/line-multi.json').then(r=>r.json());
      const bar=await fetch('./public/generated/specs/bar-signed.json').then(r=>r.json());
      line.title='Example chart';
      const draw=(spec,p)=>new XMLSerializer().serializeToString(renderNativeChart(spec,p,{outlines:atlas}).svg).replaceAll(/chart-demo-\\d+/g,'chart');
      const failures=[];
      for(const c of ALL_CONTROLS){
        const spec=c.group==='bar'?bar:line,p=structuredClone(profile),before=draw(spec,p);
        const current=effectiveValue(p,c);
        setPath(p,c.path,c.kind==='choice'?'bold':c.integer?(current===3?4:3):current+(c.step||.1)*2);
        if(draw(spec,p)===before)failures.push(c.path);
      }
      return {failures,svg:window.__lab.lastGood.svg};
    }''')
    assert result['failures']==[]
    assert '<text' not in result['svg']
    assert 'data-chart-text' in result['svg']
    assert integrated.export_bundle()['environment']['renderer']=='browser.svg-outlines'
    assert 'undefined' not in integrated.export_text()
