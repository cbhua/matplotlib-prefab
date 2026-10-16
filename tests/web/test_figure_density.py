"""Physical space-use heuristic: conservative for small panels and busy plots."""
import copy
import pytest
from conftest import needs_browser,needs_fonts
from lab import open_lab
pytestmark=[needs_browser,needs_fonts]


def check(reply):
    assert reply['result']['ok'],reply
    return next((c for c in reply['result']['report']['checks'] if c['id'].endswith('.space_utilization')),None)


def test_density_distinguishes_large_sparse_and_compact_or_busy_figures():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render()
        profile=lab.profile();profile['canvas'].update(width_mm=160,aspect_ratio=1)
        sparse={'schema_version':'1','kind':'scatter','x_label':'x','y_label':'y','x':[0,1,2],'series':[{'name':'A','y':[0,1,2]}]}
        warning=check(lab.render_once(sparse,profile))
        assert warning and warning['measurements']['empty_fraction']>=.65
        assert warning['measurements']['largest_empty_rectangle_fraction']>=.24
        compact=copy.deepcopy(profile);compact['canvas'].update(width_mm=70,aspect_ratio=.65)
        assert check(lab.render_once(sparse,compact)) is None
        busy=copy.deepcopy(sparse);busy['x']=[i%15 for i in range(225)];busy['series'][0]['y']=[i//15 for i in range(225)]
        assert check(lab.render_once(busy,profile)) is None
        line=copy.deepcopy(sparse);line['kind']='line';line['x']=list(range(30));line['series'][0]['y']=[i%2 for i in range(30)]
        assert check(lab.render_once(line,profile)) is None
        bars={'schema_version':'1','kind':'bar','x_label':'x','y_label':'y','categories':[str(i) for i in range(15)],'values':[10]*15}
        assert check(lab.render_once(bars,profile)) is None
        # Each grid panel is small, even though the whole canvas is large.
        grid={'schema_version':'1','kind':'grid','rows':2,'columns':2,'panels':[sparse]*4}
        assert check(lab.render_once(grid,profile)) is None


def test_density_warning_localization_region_and_export():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render();p=lab.page
        p.locator('#figure-width').fill('170');p.locator('#figure-height').fill('170');lab.wait_for_render()
        warnings=[c for c in lab.export_bundle()['render']['checks']['checks'] if c['id'].endswith('.space_utilization')]
        assert len(warnings)==1
        region=warnings[0]['region'];assert region['width']>0 and region['height']>0
        p.click('#ui-language')
        card=p.locator('.warning-card').filter(has_text='空间利用率偏低')
        assert card.is_visible()
        assert '连续空白' in card.inner_text()
        card.hover();assert p.locator('[data-issue-overlay] rect').count()==1
        assert 'data-issue-overlay' not in lab.wait_for_render()['svg']
        original=warnings[0]['measurements']
        p.locator('#zoom').fill('0.4');p.locator('#zoom').dispatch_event('input')
        assert next(c for c in lab.export_bundle()['render']['checks']['checks'] if c['id'].endswith('.space_utilization'))['measurements']==original
        p.click('#reset-size');lab.wait_for_render()
        assert not any(c['id'].endswith('.space_utilization') for c in lab.export_bundle()['render']['checks']['checks'])
        assert not lab.page_errors


def test_overdraw_is_detected_before_opaque_marks_hide_duplicates():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render()
        profile=lab.profile();profile['canvas'].update(width_mm=90,aspect_ratio=.75)
        spec={'schema_version':'1','kind':'scatter','x_label':'x','y_label':'y',
              'x':[0,1]+[.3+.006*(i%10) for i in range(100)],
              'series':[{'name':'A','y':[0,1]+[.3+.006*(i//10) for i in range(100)]}]}
        report=lab.render_once(spec,profile)['result']['report']
        warning=next(c for c in report['checks'] if c['id'].endswith('.mark_overdraw'))
        assert warning['measurements']['overdraw_fraction']>=.25
        assert warning['region']['width']>0
        assert report['visual_density']['panels'][0]['marks']['mark_count']==102
        assert report['visual_density']['panels'][0]['ink']['status']=='measured'
        profile['lines']['marker_size_pt']=.75
        reply=lab.render_once(spec,profile)['result']
        assert not any(c['id'].endswith('.mark_overdraw') for c in reply['report']['checks'])
        assert reply['resolved_spec']==spec
        # Dense solid bars have high ink coverage but are not overlapping marks.
        bars={'schema_version':'1','kind':'bar','x_label':'x','y_label':'y','categories':['A','B','C'],'values':[10,10,10]}
        report=lab.render_once(bars,profile)['result']['report']
        assert not any(c['id'].endswith('.mark_overdraw') for c in report['checks'])
        # A mixed grid reports density and crowding for the affected panel only.
        profile['canvas'].update(width_mm=160,aspect_ratio=.5)
        profile['lines']['marker_size_pt']=4
        grid={'schema_version':'1','kind':'grid','rows':1,'columns':2,'panels':[spec,bars]}
        report=lab.render_once(grid,profile)['result']['report']
        assert [p['kind'] for p in report['visual_density']['panels']]==['scatter','bar']
        assert [c['panel_index'] for c in report['checks'] if c['id'].endswith('.mark_overdraw')]==[0]


def test_ink_body_reference_zoom_and_agent_handoff():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render();p=lab.page
        density=lab.export_bundle()['render']['checks']['visual_density']
        assert density['body_reference']['status']=='measured'
        assert density['body_reference']['method']=='representative-prose-strip'
        assert 0<density['body_reference']['ink_fraction']<.5
        assert 0<density['panels'][0]['ink']['ink_fraction']<1
        assert density['comparisons'][0]['ink_to_body_ratio']>0
        p.locator('#zoom').fill('1.5');p.locator('#zoom').dispatch_event('input')
        assert lab.export_bundle()['render']['checks']['visual_density']==density
        assert p.locator('.density-card').is_visible()
        assert 'Body reference ink:' in p.locator('#density-readout').inner_text()
        p.click('#ui-language')
        assert '正文参照墨量' in p.locator('#density-readout').inner_text()
        assert '目标值' in p.locator('.density-card .panel-note').inner_text()
        assert 'visual_density' in lab.export_text()
        assert 'not information or a target density' in lab.export_text()
        assert not lab.page_errors


def test_raster_diagnostic_failure_does_not_fail_rendering():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render()
        lab.page.evaluate("""()=>{const original=URL.createObjectURL;URL.createObjectURL=blob=>{if(blob.type==='image/svg+xml')throw Error('Test raster unavailable');return original(blob)};}""")
        reply=lab.render_once(lab.spec(),lab.profile())['result']
        assert reply['ok']
        assert reply['report']['visual_density']['panels'][0]['ink']['status']=='not_checked'
        assert reply['report']['counts']['not_checked']==2


def test_pixel_coverage_is_not_an_order_or_information_score():
    with open_lab() as lab:
        metrics=lab.page.evaluate("""async()=>{
          const {measurePixels}=await import('./src/visual-density.js');
          const image=(paint)=>{const bytes=new Uint8ClampedArray(16*16*4);bytes.fill(255);for(let y=0;y<16;y++)for(let x=0;x<16;x++)if(paint(x,y))for(let c=0;c<3;c++)bytes[(y*16+x)*4+c]=0;return measurePixels(bytes,16,16)};
          return {blank:image(()=>false),solid:image(()=>true),block:image(x=>x<8),stripe:image(x=>x%2===0)};
        }""")
        assert metrics['blank']['ink_fraction']==0
        assert metrics['solid']['ink_fraction']==1
        assert metrics['block']['ink_fraction']==metrics['stripe']['ink_fraction']==.5
        assert metrics['stripe']['edge_transition_fraction']>metrics['block']['edge_transition_fraction']
