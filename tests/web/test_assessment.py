"""Assessment states, warning disclosure, single handoff and scatter example."""
import json
from pathlib import Path
import pytest
from conftest import needs_browser,needs_fonts,REPO_ROOT
from lab import open_lab
pytestmark=[needs_browser,needs_fonts]


def test_assessment_handoff_and_scatter():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render();p=lab.page
        assert p.locator('.buttons button').all_text_contents()==['🤖 Copy for Agents']
        assert p.locator('#figure-assessment').inner_text()=='✅ Nice figure!'
        p.select_option('#example','scatter');lab.wait_for_render()
        assert lab.spec()['kind']=='scatter'
        assert p.locator('.data-marker').count()==24
        assert p.locator('.data-line').count()==0
        assert p.locator('.reflow-slot text').count()==0
        assert p.locator('[data-path="lines.data_linewidth_pt"] input[type=range]').is_disabled()
        assert not p.locator('[data-path="lines.marker_size_pt"] input[type=range]').is_disabled()
        assert '"kind": "scatter"' in lab.export_text()
        # Point size remains a physical point size when the canvas is resized.
        before=p.locator('.data-marker').first.get_attribute('transform').split('scale')[1]
        p.locator('#figure-height').fill('100');lab.wait_for_render()
        assert p.locator('.data-marker').first.get_attribute('transform').split('scale')[1]==before
        assert p.locator('.figure-content select').first.evaluate('(n)=>getComputedStyle(n).backgroundPosition')=='calc(100% - 12px) 50%'
        # Rapid selection keeps the latest requested example and assessment.
        p.evaluate("""()=>{const select=document.querySelector('#example');for(const name of ['line-many','scatter']){select.value=name;select.dispatchEvent(new Event('change'));}}""")
        lab.wait_for_render()
        assert lab.spec()['kind']=='scatter'
        assert p.locator('.data-marker').count()==24
        assert not lab.page_errors


def test_warning_count_disclosure_and_recovery():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render();p=lab.page
        spec=json.loads((Path(REPO_ROOT)/'tests/data/bar-signed.json').read_text())
        spec['x_label']='A long axis label that extends outside the narrow figure canvas'
        p.set_input_files('#spec-file',{'name':'example.json','mimeType':'application/json','buffer':json.dumps(spec).encode()})
        lab.wait_for_render()
        lab.set_control('fonts.size_xtick_pt',12);lab.set_control('fonts.size_ytick_pt',3);lab.wait_for_render()
        checks=lab.export_bundle()['render']['checks']['checks'];warnings=[c for c in checks if c['status']=='warn']
        assert {c['title'] for c in warnings}=={'Text overlap','Text outside figure','Text too small'}
        assert p.locator('#figure-assessment').inner_text()=='⚠️ There are 3 warnings.'
        assert p.locator('#warning-rail').is_visible()
        box=p.locator('.side').bounding_box()
        p.click('#figure-assessment')
        assert p.locator('#warning-rail').is_visible()
        assert p.locator('.warning-card').count()==3
        p.locator('.warning-card').filter(has_text='Text overlap').hover()
        assert p.locator('[data-issue-overlay] rect').count()>0
        assert 'data-issue-overlay' not in lab.wait_for_render()['svg']
        p.locator('#figure-assessment').hover()
        assert p.locator('[data-issue-overlay]').count()==0
        rail=p.locator('#warning-rail').bounding_box();paper=p.locator('.reflow-paper').bounding_box()
        assert rail['x']+rail['width']<paper['x']
        assert p.locator('.side').bounding_box()==box
        folder=Path('.tmp/interface');folder.mkdir(exist_ok=True,parents=True)
        p.screenshot(path=str(folder/'warnings.png'),animations='disabled')
        lab.set_control('fonts.size_xtick_pt',8);lab.set_control('fonts.size_ytick_pt',8)
        p.select_option('#example','line-multi');lab.wait_for_render()
        assert p.locator('#figure-assessment').inner_text()=='✅ Nice figure!'
        assert p.locator('#warning-rail').is_hidden()
        assert p.locator('#figure-assessment').get_attribute('aria-expanded')=='false'
        assert not lab.page_errors
