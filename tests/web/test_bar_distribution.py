"""Default category labels and descriptive bar-space interfaces preserve data."""
import copy
import json
from pathlib import Path
import pytest
from conftest import needs_browser,needs_fonts,REPO_ROOT
from lab import open_lab
pytestmark=[needs_browser,needs_fonts]


def test_default_bar_examples_rotate_and_are_legible_at_all_template_widths():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render();p=lab.page
        fixtures=[json.loads((Path(REPO_ROOT)/'tests/data'/f'{name}.json').read_text()) for name in ['bar-signed','bar-positive']]
        profile=lab.profile()
        assert profile['bar']['category_label_rotation_deg']==30
        for width in [69.85,82.55,139.7,171.45]:
            profile['canvas'].update(width_mm=width,aspect_ratio=.618)
            for spec in fixtures:
                result=lab.render_once(spec,profile)['result']
                assert result['ok']
                assert not any(c['id'].endswith(('.tick_label_overlap','.text_within_canvas')) for c in result['report']['checks']), (width,spec['categories'],result['report']['checks'])
                assert result['resolved_spec']==spec
        p.select_option('#example','bar-signed');lab.wait_for_render()
        assert p.locator('.density-card').is_visible()
        assert 'Categories: 5' in p.locator('#density-readout').inner_text()
        assert 'rotate(-30' in lab.wait_for_render()['svg']
        p.click('#ui-language')
        assert '类别数：5' in p.locator('#density-readout').inner_text()


def test_bar_geometry_distributions_are_not_information_verdicts():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render()
        profile=lab.profile();profile['canvas'].update(width_mm=160,aspect_ratio=.8)
        spec={'schema_version':'1','kind':'bar','x_label':'x','y_label':'y','categories':['A','B'],'values':[10,10]}
        report=lab.render_once(spec,profile)['result']['report']
        metrics=report['visual_density']['panels'][0]['bar_distribution']
        assert metrics['category_count']==metrics['nonzero_bar_count']==2
        assert metrics['width_per_category_mm']==pytest.approx(metrics['plot_width_mm']/2)
        assert metrics['area_per_category_mm2']==pytest.approx(metrics['plot_area_mm2']/2)
        assert sum(metrics['horizontal_load'])/len(metrics['horizontal_load'])==pytest.approx(metrics['bar_fill_fraction'])
        assert sum(metrics['vertical_load'])/len(metrics['vertical_load'])==pytest.approx(metrics['bar_fill_fraction'])
        assert all(0<=x<=1 for x in metrics['horizontal_load']+metrics['vertical_load'])
        assert metrics['maximum_horizontal_gap_mm']>0
        zero=copy.deepcopy(spec);zero['values']=[0,0]
        result=lab.render_once(zero,profile)['result']
        empty=result['report']['visual_density']['panels'][0]['bar_distribution']
        assert empty['category_count']==2 and empty['nonzero_bar_count']==0
        assert empty['bar_fill_fraction']==0
        assert empty['maximum_horizontal_gap_mm']==pytest.approx(empty['plot_width_mm'])
        assert result['resolved_spec']==zero
        signed=copy.deepcopy(spec);signed['values']=[-2,3]
        result=lab.render_once(signed,profile)['result']
        assert result['resolved_spec']==signed
        assert result['report']['visual_density']['panels'][0]['bar_distribution']['nonzero_bar_count']==2
        # A line panel cannot accidentally receive bar distribution measurements.
        assert lab.render_once(lab.spec(),profile)['result']['report']['visual_density']['panels'][0]['bar_distribution'] is None
