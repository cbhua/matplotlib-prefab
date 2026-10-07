"""Responsive fit and stable controls while a chart is being redrawn."""
import pytest
from pathlib import Path
from conftest import needs_browser,needs_fonts
from lab import open_lab
pytestmark=[needs_browser,needs_fonts]

@pytest.mark.parametrize('viewport',[(1500,1000),(1920,1080),(2560,1440),(1280,800),(390,844)])
def test_initial_fit_and_centered_workspace(viewport):
    with open_lab(viewport=viewport) as lab:
        p=lab.page;p.wait_for_selector('[data-venue="icml2026"]');p.click('[data-venue="icml2026"]')
        assert 'mm' not in p.locator('.width-choices').inner_text()
        lab.wait_ready();lab.wait_for_render()
        g=p.evaluate('''()=>{
          const rect=s=>{const r=document.querySelector(s).getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom};};
          return {layout:rect('#editor .layout'),paper:rect('.reflow-paper'),zoom:rect('.preview-tools'),preview:rect('#preview'),height:innerHeight,width:innerWidth};
        }''')
        assert g['paper']['width']==pytest.approx(g['preview']['width']-16,abs=12)
        assert g['paper']['width']<=g['preview']['width']
        assert abs(g['zoom']['x']+g['zoom']['width']/2-(g['paper']['x']+g['paper']['width']/2))<2
        assert g['zoom']['bottom']<=g['paper']['y']
        assert abs(g['layout']['x']+g['layout']['width']/2-viewport[0]/2)<2
        if viewport[0]>900:
            expected=min(viewport[0]-48,max(860,min(1440,viewport[0]*.6)))
            assert g['layout']['width']==pytest.approx(expected,abs=1)
        assert p.evaluate('document.documentElement.scrollWidth<=innerWidth')
        folder=Path('.tmp/interface');folder.mkdir(exist_ok=True,parents=True)
        p.screenshot(path=str(folder/f'centered-{viewport[0]}.png'),animations='disabled')
        # Manually chosen zoom must survive a figure redraw and window resize.
        p.locator('#zoom').fill('0.45');p.locator('#zoom').dispatch_event('input')
        lab.set_control('lines.data_linewidth_pt',2);lab.wait_for_render()
        p.set_viewport_size({'width':viewport[0]-30,'height':viewport[1]})
        assert p.locator('#zoom').input_value()=='0.45'
        assert not lab.page_errors


def test_controls_do_not_move_while_dragging():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render();p=lab.page
        slider=p.locator('[data-path="lines.data_linewidth_pt"] input[type=range]')
        slider.scroll_into_view_if_needed()
        measure='''()=>({height:document.querySelector('.side .card').getBoundingClientRect().height,
          scroll:document.querySelector('.side').scrollTop,
          top:document.querySelector('[data-path="lines.data_linewidth_pt"]').getBoundingClientRect().top})'''
        before=p.evaluate(measure)
        box=slider.bounding_box();p.mouse.move(box['x']+box['width']*.2,box['y']+box['height']/2);p.mouse.down()
        for fraction in [.3,.5,.7,.9]:
            p.mouse.move(box['x']+box['width']*fraction,box['y']+box['height']/2)
            pending=p.evaluate(measure)
            assert pending==pytest.approx(before,abs=.5)
        p.mouse.up();lab.wait_for_render()
        assert p.evaluate(measure)==pytest.approx(before,abs=.5)
        widths=p.locator('.control-inputs input[type=range]:not(.weight-slider)').evaluate_all('(nodes)=>nodes.map(n=>n.getBoundingClientRect().width).filter(w=>w>0)')
        assert max(widths)-min(widths)<.5
        assert not lab.page_errors
