"""The real placement selector, shared styles, bounds, and agent round trip."""
import copy
import json
from pathlib import Path

import pytest
import figure_core
import import_handoff
import render
from conftest import needs_browser, needs_fonts, REPO_ROOT
from lab import open_lab

pytestmark = [needs_browser, needs_fonts]


def test_selector_default_narrow_fit_language_and_reset():
    with open_lab() as lab:
        lab.wait_ready(); lab.select('iclr2026', 'narrow'); lab.wait_for_render(); p = lab.page
        selector = p.locator('#control-legend-placement')
        assert selector.locator('input:checked').input_value() == 'inside'
        assert p.locator('[data-path="legend.side"]').is_hidden()
        original_spec, original_profile = lab.spec(), lab.profile()
        selector.locator('label').filter(has_text='Separate legend').click(); lab.wait_for_render()
        assert p.locator('.figure-panel .legend').count() == 0
        assert p.locator('.figure-legend .legend').count() == 1
        assert p.locator('.legend-frame').is_visible()
        assert p.locator('.figure-legend').get_attribute('data-side') == 'bottom'
        assert lab.spec() == original_spec
        assert lab.profile()['canvas'] == original_profile['canvas']
        bounds = p.evaluate('''()=>{
          const legend=document.querySelector('.figure-legend').getBoundingClientRect();
          const panel=document.querySelector('.figure-panel').getBoundingClientRect();
          const svg=document.querySelector('.reflow-slot > svg').getBoundingClientRect();
          return {separate:legend.top>=panel.bottom,inside:legend.left>=svg.left-.5&&legend.right<=svg.right+.5&&legend.bottom<=svg.bottom+.5};
        }''')
        assert bounds == {'separate': True, 'inside': True}
        assert not any(c['id'].endswith('.legend_data_overlap') for c in lab.export_bundle()['render']['checks']['checks'])
        p.click('#ui-language')
        assert selector.locator('span').all_text_contents() == ['图内', '独立图例']
        assert p.locator('#control-legend-side input[type=radio]').count()==4
        assert p.locator('#control-legend-side span').all_text_contents()==['上','下','左','右']
        folder = Path('.tmp/legend-placement'); folder.mkdir(parents=True, exist_ok=True)
        p.screenshot(path=str(folder/'outside-narrow.png'), animations='disabled')
        p.click('#undo-style'); lab.wait_for_render()
        assert selector.locator('input:checked').input_value() == 'inside'
        assert p.locator('.figure-panel .legend').count() == 1
        assert p.locator('.figure-legend').count() == 0
        p.locator('#control-legend-placement-outside').check(); lab.wait_for_render()
        p.locator('[data-path="legend.placement"] .control-reset').click(); lab.wait_for_render()
        assert selector.locator('input:checked').input_value() == 'inside'
        p.select_option('#example', 'bar-signed'); lab.wait_for_render()
        assert p.locator('[data-group="legend"]').is_hidden()
        assert not lab.page_errors


def test_shared_legend_styles_names_and_python_agree():
    with open_lab() as lab:
        lab.wait_ready(); lab.wait_for_render()
        line = lab.spec(); changed = copy.deepcopy(line); changed['series'].reverse()
        spec = {'schema_version':'1','kind':'grid','rows':1,'columns':3,
                'panels':[line, copy.deepcopy(line), changed]}
        profile = lab.profile(); profile['canvas'].update(width_mm=220, aspect_ratio=.5)
        profile['legend'].update(placement='outside', side='right')
        result = lab.render_once(spec, profile)['result']
        assert result['ok'], result
        entries = result['drawn']['legend']['entries']
        assert entries == figure_core.outside_legend_entries(spec, profile)
        assert len(entries) == 5
        assert result['resolved_spec'] == spec and result['resolved_profile'] == profile
        assert result['svg'].count('class="legend legend-outside"') == 1
        assert result['drawn']['legend']['side'] == 'right'
        # Repeated names in another style retain separate, panel-qualified handles.
        assert any(e['name'].startswith('Panel 1:1, 1:2 - ') for e in entries)
        single = {**line, 'series':line['series'][:1]}
        result = lab.render_once(single, profile)['result']
        assert len(result['drawn']['legend']['entries']) == 1
        profile['legend']['placement'] = 'diagonal'
        assert not lab.render_once(line, profile)['result']['ok']


@pytest.mark.parametrize('mixed', [False, True])
def test_external_legend_handoff_and_python_export(tmp_path, mixed):
    with open_lab() as lab:
        p = lab.page
        if mixed:
            p.wait_for_selector('#setup-next')
            p.click('[data-venue="icml2026"]'); p.click('[data-grid="1x2"]'); p.click('[data-layout="wide"]'); p.click('#setup-next')
        lab.wait_ready(); lab.wait_for_render()
        if mixed:
            p.select_option('#active-panel','1'); p.select_option('#example','scatter'); lab.wait_for_render()
        p.locator('#control-legend-placement-outside').check(); lab.wait_for_render()
        bundle = lab.export_bundle()
        extracted = import_handoff.extract_handoff(lab.export_text())
        assert extracted['profile']['legend']['placement'] == 'outside'
        folder = Path('.tmp/legend-placement'); folder.mkdir(parents=True, exist_ok=True)
        p.screenshot(path=str(folder/f'outside-mixed-{mixed}.png'), animations='disabled')
    import_handoff.write_handoff(extracted, tmp_path/'input')
    report = render.render(str(tmp_path/'input/spec.json'), str(tmp_path/'output'), str(tmp_path/'input/profile.json'))
    assert report['status'] != 'fail'
    assert json.loads((tmp_path/'output/spec.json').read_text()) == bundle['spec']
    from pypdf import PdfReader
    box = PdfReader(tmp_path/'output/figure.pdf').pages[0].mediabox
    assert float(box.width)*25.4/72 == pytest.approx(bundle['target']['figure_width_mm'], abs=.001)
    assert float(box.height)*25.4/72 == pytest.approx(bundle['target']['figure_height_mm'], abs=.001)


def test_unfit_legend_reports_recoverable_error():
    with open_lab() as lab:
        lab.wait_ready(); lab.wait_for_render(); p = lab.page
        original = lab.spec()
        p.locator('#figure-width').fill('30'); p.locator('#figure-height').fill('18')
        p.locator('#control-legend-placement-outside').check()
        p.wait_for_function("document.querySelector('#figure-assessment').dataset.state==='error'")
        assert 'Not enough room for a separate legend' in p.locator('#status').inner_text()
        assert p.locator('#copy-handoff').is_disabled()
        assert lab.spec() == original
        p.locator('#figure-width').fill('140'); p.locator('#figure-height').fill('85'); lab.wait_for_render()
        assert lab.export_ready()
        assert p.locator('.figure-legend .legend').count() == 1


@pytest.mark.parametrize('mixed', [False, True])
def test_four_radio_sides_place_legend_correctly_and_preserve_direction(tmp_path,mixed):
    with open_lab() as lab:
        p=lab.page
        if mixed:
            p.wait_for_selector('#setup-next');p.click('[data-venue="icml2026"]')
            p.click('[data-grid="1x2"]');p.click('[data-layout="wide"]');p.click('#setup-next')
        lab.wait_ready();lab.wait_for_render()
        p.locator('#figure-width').fill('170');p.locator('#figure-height').fill('110');lab.wait_for_render()
        p.locator('#control-legend-placement-outside').check();lab.wait_for_render()
        original=lab.spec()
        for side in ['top','bottom','left','right']:
            p.locator(f'#control-legend-side-{side}').locator('..').click();lab.wait_for_render()
            assert p.locator(f'#control-legend-side-{side}').is_checked()
            assert p.locator('#control-legend-side input:checked').count()==1
            assert p.locator('.figure-legend').get_attribute('data-side')==side
            assert lab.profile()['legend']['side']==side and lab.spec()==original
            geometry=p.evaluate('''()=>{
              const l=document.querySelector('.figure-legend').getBoundingClientRect();
              const a=[...document.querySelectorAll('.figure-panel')].map(n=>n.getBoundingClientRect());
              const s=document.querySelector('.reflow-slot > svg').getBoundingClientRect();
              return {top:l.bottom<=Math.min(...a.map(b=>b.top))+.5,
                bottom:l.top>=Math.max(...a.map(b=>b.bottom))-.5,
                left:l.right<=Math.min(...a.map(b=>b.left))+.5,
                right:l.left>=Math.max(...a.map(b=>b.right))-.5,
                inside:l.left>=s.left-.5&&l.right<=s.right+.5&&l.top>=s.top-.5&&l.bottom<=s.bottom+.5};
            }''')
            assert geometry[side] and geometry['inside'],(side,geometry)
            extracted=import_handoff.extract_handoff(lab.export_text())
            assert extracted['profile']['legend']['side']==side
            assert f'on the {side} side' in lab.export_text()
            import_handoff.write_handoff(extracted,tmp_path/side/'input')
            result=render.render(str(tmp_path/side/'input/spec.json'),str(tmp_path/side/'output'),str(tmp_path/side/'input/profile.json'))
            assert result['status']!='fail'
        # Keyboard selection uses native radio behavior and retains the requested side.
        p.locator('#control-legend-side-top').focus();p.keyboard.press('ArrowRight');lab.wait_for_render()
        assert p.locator('#control-legend-side-bottom').is_checked()
        p.locator('[data-path="legend.side"] .control-reset').click();lab.wait_for_render()
        assert p.locator('#control-legend-side-bottom').is_checked()
        folder=Path('.tmp/legend-placement');folder.mkdir(parents=True,exist_ok=True)
        p.screenshot(path=str(folder/f'four-radios-{mixed}.png'),animations='disabled')
        # A selected left side must report insufficient space, never switch to bottom.
        p.locator('#control-legend-side-left').check();lab.wait_for_render()
        p.locator('#figure-width').fill('30');p.locator('#figure-height').fill('80')
        p.wait_for_function("document.querySelector('#figure-assessment').dataset.state==='error'")
        assert lab.profile()['legend']['side']=='left'
        assert p.locator('#copy-handoff').is_disabled()
        assert not lab.page_errors
