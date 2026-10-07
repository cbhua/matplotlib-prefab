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
