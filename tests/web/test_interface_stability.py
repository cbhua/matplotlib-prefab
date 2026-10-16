"""Responsive fit and stable controls while a chart is being redrawn."""
import pytest
from pathlib import Path
from conftest import needs_browser,needs_fonts
from lab import open_lab
pytestmark=[needs_browser,needs_fonts]

@pytest.mark.parametrize('viewport',[(1500,1000),(1920,1080),(2560,1440),(2560,800),(1280,800),(1024,768),(390,844)])
def test_initial_fit_and_centered_workspace(viewport):
    with open_lab(viewport=viewport) as lab:
        p=lab.page;p.wait_for_selector('[data-venue="icml2026"]');p.click('[data-venue="icml2026"]')
        assert 'mm' not in p.locator('.width-choices').inner_text()
        lab.wait_ready();lab.wait_for_render()
        g=p.evaluate('''()=>{
          const rect=s=>{const r=document.querySelector(s).getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom};};
          return {header:rect('.site-header-inner'),layout:rect('#editor .layout'),paper:rect('.reflow-paper'),zoom:rect('.preview-tools'),preview:rect('#preview'),viewport:rect('#paper-viewport'),height:innerHeight,width:innerWidth};
        }''')
        # Fit width even when a short viewport requires vertical scrolling.
        assert abs(g['paper']['width']-(g['viewport']['width']-18))<12
        if viewport==(2560,800):
            assert g['paper']['bottom']>g['viewport']['bottom']
        assert g['paper']['width']<=g['preview']['width']
        assert abs(g['zoom']['x']+g['zoom']['width']/2-(g['paper']['x']+g['paper']['width']/2))<2
        assert g['zoom']['bottom']<=g['paper']['y']
        assert g['header']['x']==pytest.approx(g['layout']['x'],abs=1)
        assert g['header']['right']==pytest.approx(g['layout']['right'],abs=1)
        if viewport[0]>900:
            expected=(viewport[0]-208 if viewport[0]<1280 else min(viewport[0]-48,max(860,min(1440,viewport[0]*.6))))
            assert g['layout']['width']==pytest.approx(expected,abs=1)
            assert g['layout']['bottom']==pytest.approx(viewport[1]-16,abs=1)
            lab.set_control('fonts.size_xtick_pt',4);lab.wait_for_render()
            rail=p.locator('#warning-rail').bounding_box()
            assert rail['x']>=0
            assert rail['x']+rail['width']<g['layout']['x']
            lab.reset_all();lab.wait_for_render()
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


@pytest.mark.parametrize('viewport',[(1500,1000),(2560,800),(390,844)])
def test_zoom_centers_oversized_paper_and_reset_restores_auto_fit(viewport):
    with open_lab(viewport=viewport) as lab:
        lab.wait_ready();lab.wait_for_render();p=lab.page
        initial=float(p.locator('#zoom').input_value())
        measure='''()=>{
          const viewport=document.querySelector('#paper-viewport'),v=viewport.getBoundingClientRect();
          const paper=document.querySelector('.reflow-paper').getBoundingClientRect();
          const tools=document.querySelector('.preview-tools').getBoundingClientRect();
          return {centerError:paper.x+paper.width/2-(v.x+v.width/2),
            top:paper.top,viewportTop:v.top,bottom:paper.bottom,viewportBottom:v.bottom,
            viewportWidth:v.width,paperWidth:paper.width,scrollLeft:viewport.scrollLeft,
            scrollTop:viewport.scrollTop,toolsBottom:tools.bottom};
        }'''
        for zoom in ['1.5','1.6']:
            p.locator('#zoom').fill(zoom);p.locator('#zoom').dispatch_event('input')
            g=p.evaluate(measure)
            assert abs(g['centerError'])<2
            assert g['scrollLeft']>0
            assert g['top']==pytest.approx(g['viewportTop']+9,abs=1)
            assert g['toolsBottom']<=g['viewportTop']
            assert p.locator('#reset-zoom').is_visible()
        folder=Path('.tmp/interface');folder.mkdir(exist_ok=True,parents=True)
        p.screenshot(path=str(folder/f'zoomed-{viewport[0]}.png'),animations='disabled')
        # Reset returns to the top after both horizontal and vertical panning.
        p.locator('#paper-viewport').evaluate('(n)=>{n.scrollTop=200;n.scrollLeft=0}')
        p.click('#reset-zoom')
        assert float(p.locator('#zoom').input_value())==pytest.approx(initial)
        g=p.evaluate(measure)
        assert abs(g['centerError'])<2
        assert g['scrollTop']==0
        assert g['scrollLeft']==0
        assert abs(g['paperWidth']-(g['viewportWidth']-18))<12
        assert g['paperWidth']<=g['viewportWidth']
        p.screenshot(path=str(folder/f'zoom-reset-{viewport[0]}.png'),animations='disabled')
        # Auto fit follows width changes, independently of available height.
        p.set_viewport_size({'width':viewport[0]-30,'height':600})
        p.wait_for_function("Math.abs(document.querySelector('.reflow-paper').getBoundingClientRect().width-(document.querySelector('#paper-viewport').clientWidth-16))<12")
        assert p.locator('#paper-viewport').evaluate('(n)=>getComputedStyle(n).backgroundSize')=='16px 16px, 16px 16px'
        assert not lab.page_errors
