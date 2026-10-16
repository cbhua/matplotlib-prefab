"""Legend collisions inspect rendered data footprints, not path bounding boxes."""
import json
from pathlib import Path
import pytest
from conftest import needs_browser,needs_fonts
from lab import open_lab
pytestmark=[needs_browser,needs_fonts]


def test_legend_collision_uses_actual_strokes_markers_and_plot_clip():
    with open_lab() as lab:
        result=lab.page.evaluate('''async()=>{
          const {measureLegendOverlap}=await import('./src/figure-occlusion.js');
          const ns='http://www.w3.org/2000/svg';
          function measure(data,options={}){
            const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 100 100');svg.setAttribute('width','100');svg.setAttribute('height','100');
            svg.innerHTML=`<g class="data">${data}</g><g class="legend"><rect x="40" y="10" width="30" height="20" fill="white"/><line x1="45" y1="20" x2="60" y2="20" stroke="black"/></g>`;
            document.body.append(svg);
            const g={left:options.left??0,right:100,top:0,bottom:100};
            const a=measureLegendOverlap(svg,g);
            svg.style.transform='scale(.37)';const b=measureLegendOverlap(svg,g);svg.remove();
            return {a,b};
          }
          const line=(d,extra='')=>`<path class="data-line" data-series="0" d="${d}" fill="none" stroke="black" stroke-width="1" ${extra}/>`;
          return {
            crossing:measure(line('M0 20L100 20')),
            bboxOnly:measure(line('M0 0L100 0L100 100')),
            dashGap:measure(line('M0 20L100 20','stroke-dasharray="10 90"')),
            thickEdge:measure(line('M0 9.7L100 9.7')),
            clipped:measure(line('M40 20L50 20'),{left:60}),
            marker:measure('<circle class="data-marker" data-series="1" cx="38" cy="20" r="5" fill="blue"/>'),
            ownHandle:measure(''),
            invisible:measure(line('M0 20L100 20','opacity="0"')),
            grid:measure('<path class="grid-line" d="M0 20L100 20" stroke="black"/>'),
          };
        }''')
        for key in ['crossing','thickEdge','marker']:
            assert result[key]['a']['overlaps'],key
            assert result[key]['a']['overlap_area_pt2']>0
            assert result[key]['a']==result[key]['b']
        for key in ['bboxOnly','dashGap','clipped','ownHandle','invisible','grid']:
            assert not result[key]['a']['overlaps'],key
        assert result['crossing']['a']['affected_primitives']['lines']==1
        assert result['marker']['a']['affected_primitives']['markers']==1
        assert result['marker']['a']['series_indices']==[1]


def test_compressed_real_plot_warns_and_grid_identifies_only_affected_panel():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render()
        spec=lab.spec();profile=lab.profile()
        profile['canvas'].update(width_mm=70,aspect_ratio=30/70)
        for frame in [False,True]:
            profile['legend']['frame']=frame
            reply=lab.render_once(spec,profile)['result']
            warning=next(c for c in reply['report']['checks'] if c['id'].endswith('.legend_data_overlap'))
            assert warning['measurements']['affected_primitives']['lines']>0
            assert reply['resolved_spec']==spec
        profile['canvas']['aspect_ratio']=1
        reply=lab.render_once(spec,profile)['result']
        assert not any(c['id'].endswith('.legend_data_overlap') for c in reply['report']['checks'])
        single={**spec,'series':spec['series'][:1]}
        profile['canvas'].update(width_mm=140,aspect_ratio=30/140)
        grid={'schema_version':'1','kind':'grid','rows':1,'columns':2,'panels':[spec,single]}
        reply=lab.render_once(grid,profile)['result']
        warnings=[c for c in reply['report']['checks'] if c['id'].endswith('.legend_data_overlap')]
        assert [c['panel_index'] for c in warnings]==[0]


def test_legend_warning_card_highlight_language_export_and_recovery():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render();p=lab.page
        original=lab.spec()
        p.locator('#figure-width').fill('70');p.locator('#figure-height').fill('30');lab.wait_for_render()
        card=p.locator('.warning-card').filter(has_text='Legend overlaps data')
        assert card.is_visible()
        assert card.locator('strong').inner_text()=='⚠️ Legend overlaps data'
        check=next(c for c in lab.export_bundle()['render']['checks']['checks'] if c['id'].endswith('.legend_data_overlap'))
        assert check['panel_index']==0
        card.hover()
        assert p.locator('[data-issue-overlay] rect').count()==1
        assert 'data-issue-overlay' not in lab.wait_for_render()['svg']
        card.get_by_role('button',name='Adjust setting').click()
        assert p.locator('#figure-height').evaluate('(n)=>n===document.activeElement')
        p.locator('#zoom').fill('1.5');p.locator('#zoom').dispatch_event('input')
        assert next(c for c in lab.export_bundle()['render']['checks']['checks'] if c['id'].endswith('.legend_data_overlap'))==check
        assert 'legend_data_overlap' in lab.export_text()
        p.click('#ui-language')
        assert '图例覆盖数据' in p.locator('.warning-card').filter(has_text='图例覆盖数据').locator('strong').inner_text()
        # Locate by the translated title after changing the interface language.
        p.locator('.warning-card').filter(has_text='图例覆盖数据').hover()
        folder=Path('.tmp/interface');folder.mkdir(exist_ok=True,parents=True)
        p.screenshot(path=str(folder/'legend-overlap.png'),animations='disabled')
        p.locator('#figure-height').fill('70');lab.wait_for_render()
        assert not any(c['id'].endswith('.legend_data_overlap') for c in lab.export_bundle()['render']['checks']['checks'])
        assert lab.spec()==original
        assert not lab.page_errors
