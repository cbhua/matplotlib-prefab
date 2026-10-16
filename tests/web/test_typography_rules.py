"""Project typography preferences are role-specific, contextual, and extensible."""
import copy
import pytest
from conftest import needs_browser,needs_fonts
from lab import open_lab
pytestmark=[needs_browser,needs_fonts]


def test_relative_size_bounds_hierarchy_and_role_presence():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render()
        spec=lab.spec();profile=lab.profile()
        cases=[]
        def case(edits,expected,body=10,spec_override=None):
            p=copy.deepcopy(profile);p['fonts'].update(edits)
            cases.append({'profile':p,'spec':spec_override or spec,'body':body,'expected':expected})
        case({},[])
        case({'size_x_label_pt':8.49,'size_xtick_pt':7.5},['paper.size_x_label_pt','paper.axis_label_consistency'])
        case({'size_y_label_pt':9.51},['paper.size_y_label_pt','paper.axis_label_consistency'])
        for key,value in [('size_xtick_pt',7.49),('size_ytick_pt',8.01),('size_legend_pt',7.75),('size_legend_pt',10.25)]:
            case({key:value},['paper.'+key])
        case({'size_axis_label_pt':9,'size_tick_pt':7.5,'size_legend_pt':10},[])
        case({'size_axis_label_pt':8.5,'size_tick_pt':7.5},[])
        case({'size_axis_label_pt':9.5,'size_tick_pt':8},[])
        case({'size_x_label_pt':8.5,'size_y_label_pt':9.5,'size_tick_pt':7.5},['paper.axis_label_consistency'])
        # The 0.8 × axis-label ± 1 pt relation tightens the 8 pt upper bound to 7.8 pt.
        case({'size_axis_label_pt':8.5,'size_tick_pt':7.8},[])
        case({'size_axis_label_pt':8.5,'size_xtick_pt':7.81,'size_ytick_pt':7.8},['paper.size_xtick_pt'])
        # Axis/tick recommendations are physical points; only legend retains body scaling.
        case({'size_axis_label_pt':9,'size_tick_pt':8,'size_legend_pt':9.6},[],body=12)
        # Fix a too-small axis first, without advising an impossible tick interval.
        case({'size_x_label_pt':7,'size_xtick_pt':8},['paper.size_x_label_pt','paper.axis_label_consistency'])
        single={**spec,'series':spec['series'][:1]}
        case({'size_legend_pt':3},[],spec_override=single)
        case({'size_x_label_pt':3,'size_xtick_pt':8},[],spec_override={**spec,'x_label':''})
        got=lab.page.evaluate('''async cases=>{
          const {evaluateTypography}=await import('./src/typography-checks.js');
          return cases.map(c=>evaluateTypography({preview_settings:{body_size_pt:c.body}},c.profile,c.spec));
        }''',cases)
        for c,checks in zip(cases,got):
            assert [v['id'] for v in checks]==c['expected'],(c,checks)
            for check in checks:
                if 'minimum_pt' in check['measurements']:
                    assert check['measurements']['minimum_pt']<=check['measurements']['maximum_pt']
                assert check['measurements']['body_pt']==c['body']
                assert check['category']=='typography'
            if c['profile']['fonts'].get('size_x_label_pt')==7:
                assert checks[0]['measurements']['tick_relative_constraint_deferred']


def test_typography_warning_handoff_and_absolute_check_deduplication():
    with open_lab() as lab:
        lab.wait_ready();lab.wait_for_render();p=lab.page
        lab.set_control('fonts.size_xtick_pt',7);lab.wait_for_render()
        card=p.locator('.warning-card').filter(has_text='X tick labels size is too small')
        assert '7.5–8.0 pt' in card.inner_text()
        card.get_by_role('button',name='Adjust setting').click()
        assert p.locator('[data-path="fonts.size_xtick_pt"] input[type=range]').evaluate('(n)=>n===document.activeElement')
        report=lab.export_bundle()['render']['checks']
        assert report['experience_rules']['typography']['origin']=='project-owner-preference'
        assert report['experience_rules']['typography']['tick_labels']['target_axis_label_ratio']==.8
        assert report['experience_rules']['typography']['tick_labels']['axis_label_tolerance_pt']==1
        assert report['experience_rules']['strokes']['maximum_checked_pt'] is None
        before=next(c for c in report['checks'] if c['id']=='paper.size_xtick_pt')
        p.locator('#zoom').fill('1.5');p.locator('#zoom').dispatch_event('input')
        assert next(c for c in lab.export_bundle()['render']['checks']['checks'] if c['id']=='paper.size_xtick_pt')==before
        lab.set_control('fonts.size_xtick_pt',4);lab.wait_for_render()
        checks=lab.export_bundle()['render']['checks']['checks']
        assert any(c['id']=='paper.size_xtick_pt' for c in checks)
        assert not any(c['id'].endswith('.minimum_text_size') for c in checks)
        lab.set_control('fonts.size_xtick_pt',8);lab.wait_for_render()
        assert not any(c['category']=='typography' for c in lab.export_bundle()['render']['checks']['checks'] if 'category' in c)
        assert not lab.page_errors
