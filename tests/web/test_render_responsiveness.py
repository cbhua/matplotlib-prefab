"""Style redraws retain paper DOM and physical warnings are actionable."""
import pytest
from conftest import needs_browser,needs_fonts
from lab import open_lab
pytestmark=[needs_browser,needs_fonts]


def test_style_redraw_does_not_repaginate_and_sizes_still_do():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render();p=lab.page
        p.evaluate('window.originalPaper=document.querySelector(".reflow-paper")')
        for size in [8,9,10,8]:
            lab.set_control('fonts.size_xtick_pt',size);lab.wait_for_render()
            assert p.evaluate('originalPaper===document.querySelector(".reflow-paper")')
        p.locator('#figure-height').fill('120');lab.wait_for_render()
        assert not p.evaluate('originalPaper===document.querySelector(".reflow-paper")')
        assert lab.export_bundle()['render']['checks']['paper_context_checked']
        assert p.locator('.reflow-paper').count()==1


def test_constant_data_zero_margin_and_invisible_points():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render()
        spec={'schema_version':'1','kind':'scatter','x_label':'x','y_label':'y','x':[1,1,1],'series':[{'name':'A','y':[0,0,0]}]}
        profile=lab.profile();profile['axes']['margin_x']=0;profile['axes']['margin_y']=0
        reply=lab.render_once(spec,profile)['result']
        assert reply['ok']
        assert 'NaN' not in reply['svg'] and 'Infinity' not in reply['svg']
        profile['lines']['marker_size_pt']=0
        reply=lab.render_once(spec,profile)['result']
        assert 'panel_1.invisible_data' in [c['id'] for c in reply['report']['checks']]
