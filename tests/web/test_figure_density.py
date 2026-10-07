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
