"""Checks use print units and include the paper context in the copied handoff."""
import json
from pathlib import Path
import pytest
from conftest import needs_browser,needs_fonts,REPO_ROOT
from lab import open_lab
pytestmark=[needs_browser,needs_fonts]


def warnings(lab):
    return {c['id']:c for c in lab.export_bundle()['render']['checks']['checks'] if c['status']=='warn'}


def test_paper_context_and_actionable_warnings():
    with open_lab() as lab:
        lab.wait_ready();lab.select('iclr2026','narrow');lab.wait_for_render();p=lab.page
        assert not warnings(lab)
        p.locator('#figure-width').fill('125');lab.wait_for_render()
        assert 'paper.wrap_width' in warnings(lab)
        assert lab.export_bundle()['render']['checks']['paper_context_checked']
        p.click('#figure-assessment')
        item=p.locator('.warning-card').filter(has_text='Body text is squeezed')
        item.get_by_role('button',name='Adjust setting').click()
        assert p.locator('#figure-width').evaluate('(n)=>n===document.activeElement')
        p.click('#reset-size');lab.wait_for_render()
        assert lab.profile()['canvas']['width_mm']==pytest.approx(69.85)
        assert not warnings(lab)
        # At a narrow width a long caption can reach the footer even if the SVG fits.
        p.locator('#figure-width').fill('30');p.locator('#figure-height').fill('180');lab.wait_for_render()
        assert 'paper.figure_height' in warnings(lab)
        before=set(warnings(lab))
        p.locator('#zoom').fill('0.4');p.locator('#zoom').dispatch_event('input')
        # A paper redraw at the new zoom must preserve physical-unit judgments.
        p.locator('#figure-height').fill('179');lab.wait_for_render()
        assert set(warnings(lab))==before
        assert p.locator('.reflow-paper').count()==1


def test_custom_width_spans_columns_and_handoff_is_compact():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render();p=lab.page
        p.locator('#figure-width').fill('140');lab.wait_for_render()
        bundle=lab.export_bundle()
        assert bundle['target']['float_environment']=='figure*'
        assert bundle['target']['width_rule']=='explicit physical width'
        assert bundle['data_usage']['intent']=='style-reference'
        assert bundle['data_usage']['panel_sources'][0]['kind']=='example'
        assert 'article' not in bundle['paper_preview']
        text=lab.export_text()
        assert 'illustrative fixtures' in text
        assert 'scientific-figures/SKILL.md' in text
        assert len(text)<14000
        imported=json.loads((Path(REPO_ROOT)/'tests/data/scatter.json').read_text())
        p.set_input_files('#spec-file',{'name':'real-data.json','mimeType':'application/json','buffer':json.dumps(imported).encode()})
        p.wait_for_function("window.__lab.currentSpec.kind==='scatter'");lab.wait_for_render()
        assert lab.export_bundle()['data_usage']['panel_sources'][0]['kind']=='user-import'
        assert lab.export_bundle()['data_usage']['intent']=='preserve-supplied-data'
        assert p.locator('#data-origin').inner_text()=='Imported data'
        assert lab.export_bundle()['spec']==imported


def test_style_undo_and_copy_feedback():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render();p=lab.page
        original=lab.profile()
        lab.set_control('fonts.size_x_label_pt',12);lab.wait_for_render()
        p.click('#undo-style');lab.wait_for_render()
        assert lab.profile()==original
        assert p.locator('#undo-style').is_disabled()
        p.evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.copiedHandoff=text}}})")
        p.click('#copy-handoff')
        assert p.locator('#copy-handoff').inner_text()=='Copied!'
        assert p.evaluate('window.copiedHandoff')==lab.export_text()


def test_wrapped_width_boundaries_and_caption_warning():
    with open_lab() as lab:
        lab.wait_ready(); lab.select('iclr2026','narrow'); lab.wait_for_render(); p=lab.page
        results=p.evaluate('''async()=>{
          const {evaluatePaper}=await import('./src/paper-checks.js');
          const page=window.__labApi.currentPage(),profile=window.__labApi.currentProfile(),spec=window.__labApi.currentSpec();
          return [.249,.25,1/3,2/3,.67].map(ratio=>{
            const source=structuredClone(page);source.figure.width_mm=source.text_block.width_mm*ratio;
            const warnings=evaluatePaper(source,profile,spec,document.querySelector('.reflow-paper')).filter(c=>c.rule_id==='wrapped-figure-width');
            source.layout.text_wrap=false;
            const exempt=evaluatePaper(source,profile,spec,document.querySelector('.reflow-paper')).filter(c=>c.rule_id==='wrapped-figure-width');
            return {ratio,warnings,exempt};
          });
        }''')
        assert [len(r['warnings']) for r in results]==[1,1,0,0,1]
        assert all(not r['exempt'] for r in results)
        assert results[0]['warnings'][0]['measurements']['caption_cramped']
        assert not results[1]['warnings'][0]['measurements']['caption_cramped']
        assert results[-1]['warnings'][0]['id']=='paper.wrap_width'
        p.locator('#figure-width').fill('32');lab.wait_for_render()
        card=p.locator('.warning-card').filter(has_text='Wrapped figure is too narrow')
        assert 'Below one quarter' in card.inner_text()
        card.get_by_role('button',name='Adjust setting').click()
        assert p.locator('#figure-width').evaluate('(n)=>n===document.activeElement')
        check=next(c for c in warnings(lab).values() if c['id']=='paper.wrap_figure_narrow')
        assert check['measurements']['body_width_ratio']==pytest.approx(32/139.7)
        p.locator('#figure-width').fill('100');lab.wait_for_render()
        assert 'paper.wrap_width' in warnings(lab)
        p.click('#ui-language')
        assert '2/3' in p.locator('.warning-card').filter(has_text='正文宽度').inner_text()
        p.click('#reset-size');lab.wait_for_render()
        assert not any(c['rule_id']=='wrapped-figure-width' for c in warnings(lab).values() if 'rule_id' in c)
