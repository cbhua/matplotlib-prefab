"""Browser spec acceptance agrees with the Python contract, including malformed imports."""
import copy,json
from pathlib import Path
import pytest
import figure_core
from conftest import needs_browser,needs_fonts,REPO_ROOT
from lab import open_lab
pytestmark=[needs_browser,needs_fonts]


def test_browser_contract_matches_python():
    base=json.loads((Path(REPO_ROOT)/'tests/data/line-multi.json').read_text());cases=[base]
    for field,value in [('schema_version','2'),('kind','heatmap'),('x',[]),('x',[True]),('x_label',None),('title',42),('series',None),('series',[]),('x',[0])]:
        spec=copy.deepcopy(base);spec[field]=value;cases.append(spec)
    for series in [[{'name':'A','y':['1']}],[{'name':'A','y':[0]*len(base['x'])}]*2,[{'name':'A','y':[0]*len(base['x']),'unknown':1}]]:
        spec=copy.deepcopy(base);spec['series']=series;cases.append(spec)
    spec=copy.deepcopy(base);spec['kind']='scatter';cases.append(spec)
    expected=[]
    for spec in cases:
        try:figure_core.validate_spec(spec);expected.append(True)
        except figure_core.SpecError:expected.append(False)
    with open_lab() as lab:
        got=lab.page.evaluate('''async cases=>{const {validateFigureSpec}=await import('./src/spec-validation.js');return cases.map(spec=>{try{validateFigureSpec(spec);return true;}catch{return false;}})}''',cases)
        assert got==expected


def test_rejected_import_preserves_current_figure():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render();p=lab.page
        lab.set_control('fonts.size_xtick_pt',4);lab.wait_for_render()
        before=lab.spec()
        p.set_input_files('#spec-file',{'name':'invalid.json','mimeType':'application/json','buffer':b'{"kind":"line"}'})
        p.wait_for_function("document.querySelector('#status').dataset.kind==='error'")
        assert lab.spec()==before
        assert 'schema_version' in p.locator('#status').inner_text()
        assert p.locator('#warning-rail #status').is_visible()
        assert p.locator('#warning-rail .warning-card').count()>0
        assert p.locator('#figure-assessment').get_attribute('data-state')=='error'
        assert p.locator('#copy-handoff').is_enabled()
        assert not lab.page_errors


def test_import_stays_with_the_panel_selected_when_it_started():
    with open_lab() as lab:
        p=lab.page;p.wait_for_selector('[data-venue="icml2026"]')
        p.click('[data-venue="icml2026"]');p.click('[data-grid="1x2"]')
        p.click('[data-layout="wide"]');p.click('#setup-next')
        lab.wait_ready();lab.wait_for_render()
        imported=json.loads((Path(REPO_ROOT)/'tests/data/scatter.json').read_text())
        p.evaluate("""()=>{const original=File.prototype.text;File.prototype.text=async function(){const data=await original.call(this);await new Promise(resolve=>window.releaseImport=resolve);return data;}}""")
        p.set_input_files('#spec-file',{'name':'slow.json','mimeType':'application/json','buffer':json.dumps(imported).encode()})
        p.wait_for_function("typeof window.releaseImport==='function'")
        p.select_option('#active-panel','1')
        p.evaluate('window.releaseImport()');lab.wait_for_render()
        bundle=lab.export_bundle()
        assert bundle['spec']['panels'][0]==imported
        assert bundle['spec']['panels'][1]['kind']=='line'
        assert p.locator('#data-origin').inner_text()=='Example data'
        assert p.locator('#example').input_value()=='line-multi'


@pytest.mark.parametrize('viewport',[(1500,1000),(390,844)])
def test_render_error_uses_shared_rail_and_clears_after_recovery(viewport):
    with open_lab(viewport=viewport) as lab:
        lab.wait_ready();lab.wait_for_render();p=lab.page
        imported=lab.spec();imported['x_label']='Unsupported \U0001f52c'
        p.set_input_files('#spec-file',{'name':'unsupported.json','mimeType':'application/json','buffer':json.dumps(imported).encode()})
        p.wait_for_function("document.querySelector('#status').dataset.kind==='error'")
        assert p.locator('#warning-rail #status').is_visible()
        assert 'This configuration could not be drawn.' in p.locator('#status').inner_text()
        assert p.locator('#status .status-detail').inner_text()
        assert p.locator('#status').evaluate('(n)=>getComputedStyle(n).backgroundColor')=='rgb(255, 240, 238)'
        assert p.locator('#copy-handoff').is_disabled()
        assert p.locator('#preview #status').count()==0
        assert p.locator('#figure-assessment').get_attribute('data-state')=='error'
        if viewport[0]>900:
            rail=p.locator('#warning-rail').bounding_box();layout=p.locator('#editor .layout').bounding_box()
            assert rail['x']+rail['width']<layout['x']
        p.click('#ui-language')
        assert '无法绘制当前配置' in p.locator('#status').inner_text()
        p.select_option('#example','line-multi');lab.wait_for_render()
        assert p.locator('#status').is_hidden()
        assert p.locator('#warning-rail').is_hidden()
        assert p.locator('#copy-handoff').is_enabled()
        assert not lab.page_errors


def test_renderer_start_error_retains_retry_in_shared_rail():
    with open_lab() as lab:
        p=lab.page
        p.route('**/chart-demo/text-outlines.json',lambda route:route.abort())
        p.wait_for_selector('#setup-next');p.click('#setup-next')
        p.wait_for_function("document.querySelector('#status').dataset.kind==='error'")
        assert p.locator('#warning-rail #status').is_visible()
        assert p.locator('#status #boot-retry').is_visible()
        assert 'failed to start' in p.locator('#status').inner_text()
