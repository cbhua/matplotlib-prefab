"""Separate legends reserve physical space without hiding data or changing sizes."""
import copy
import json

import pytest
import figure_core as core
import grid_core
from helpers import load_default_profile, case, render, check


@pytest.mark.parametrize('name', ['line-multi', 'line-single', 'scatter'])
@pytest.mark.parametrize('width', [69.85, 171.45])
def test_outside_single_legend_preserves_data_and_type(name, width):
    spec = json.load(open(case(name)))
    profile = load_default_profile()
    profile['canvas']['width_mm'] = width
    profile['legend']['placement'] = 'outside'
    profile['fonts'].update(size_legend_pt=8, weight_legend='bold')
    with core.drawn_figure(spec, profile) as (fig, ax, drawn):
        assert len(fig.axes) == 1 and len(fig.legends) == 1
        assert ax.get_legend() is None and drawn['legend_drawn']
        assert fig.get_size_inches() == pytest.approx(core.figure_size_inches(profile))
        renderer = __import__('inspect_figure').figure_renderer(fig)
        assert not ax.get_tightbbox(renderer).overlaps(fig.legends[0].get_window_extent(renderer))
        assert [t.get_text() for t in fig.legends[0].get_texts()] == [s['name'] for s in spec['series']]
        assert all(t.get_fontsize() == 8 and t.get_fontweight() == 'bold' for t in fig.legends[0].get_texts())
        for line, series in zip(ax.lines, spec['series']):
            assert list(line.get_xdata()) == spec['x']
            assert list(line.get_ydata()) == series['y']
        import inspect_figure
        report = inspect_figure.Report()
        inspect_figure.check_text_within_canvas(report, fig)
        assert report.checks[0]['status'] == 'pass'


def test_grid_legend_deduplicates_only_identical_names_and_styles(tmp_path):
    line = json.load(open(case('line-multi')))
    changed = copy.deepcopy(line)
    changed['series'] = list(reversed(changed['series']))
    bar = json.load(open(case('bar-signed')))
    spec = {'schema_version': '1', 'kind': 'grid', 'rows': 2, 'columns': 2,
            'panels': [line, copy.deepcopy(line), changed, bar]}
    profile = load_default_profile()
    profile['canvas']['width_mm'] = 171.45
    profile['legend']['placement'] = 'outside'
    entries = core.outside_legend_entries(spec, profile)
    # The middle series keeps its slot; the first and last change drawn styles.
    assert len(entries) == 5
    assert any(e['panel_indices'] == [0, 1, 2] for e in entries)
    assert any(e['name'].startswith('Panel 1:1, 1:2 - ') for e in entries)
    with grid_core.drawn_figure(spec, profile) as (fig, axes, drawn):
        assert len(fig.axes) == 4 and len(fig.legends) == 1
        assert len(fig.legends[0].get_texts()) == 5
        assert all(a.get_legend() is None for a in axes)
    _, report = render(tmp_path, spec, profile=profile)
    assert report['status'] != 'fail'
    assert all(c['status'] == 'pass' for c in report['checks'] if c['id'].endswith('font_sizes'))


def test_outside_legend_pdf_keeps_whole_canvas(tmp_path):
    profile = load_default_profile()
    profile['legend']['placement'] = 'outside'
    output, report = render(tmp_path, case('line-multi'), profile=profile)
    assert report['status'] != 'fail'
    assert check(report, 'legend_present')['status'] == 'pass'
    from pypdf import PdfReader
    from pathlib import Path
    box = PdfReader(Path(output)/'figure.pdf').pages[0].mediabox
    assert float(box.width)*25.4/72 == pytest.approx(profile['canvas']['width_mm'], abs=.001)
    assert float(box.height)*25.4/72 == pytest.approx(profile['canvas']['width_mm']*profile['canvas']['aspect_ratio'], abs=.001)


def test_bottom_shared_legend_keeps_mixed_grid_labels_within_canvas():
    line = json.load(open(case('line-multi')))
    bar = json.load(open(case('bar-signed')))
    spec = {'schema_version':'1','kind':'grid','rows':2,'columns':2,
            'panels':[line, bar, copy.deepcopy(line), copy.deepcopy(bar)]}
    profile = load_default_profile()
    profile['legend']['placement'] = 'outside'
    profile['canvas'].update(width_mm=90, aspect_ratio=1.5)
    with grid_core.drawn_figure(spec, profile) as (fig, axes, drawn):
        assert drawn['panels'][0]['legend_side'] == 'bottom'
        import inspect_figure
        report = inspect_figure.Report()
        inspect_figure.check_text_within_canvas(report, fig)
        assert report.checks[0]['status'] == 'pass'


def test_legacy_profiles_bars_and_unfit_legends():
    profile = load_default_profile()
    spec = json.load(open(case('line-multi')))
    legacy = copy.deepcopy(profile); del legacy['legend']['placement']
    assert core.render_to_svg(spec, legacy)['svg'] == core.render_to_svg(spec, profile)['svg']
    for value in ['left', None, True]:
        bad = copy.deepcopy(profile); bad['legend']['placement'] = value
        with pytest.raises(core.ProfileError, match='placement'):
            core.validate_profile(bad)
    profile['legend']['placement'] = 'outside'
    bar = json.load(open(case('bar-signed')))
    with core.drawn_figure(bar, profile) as (fig, _, _):
        assert not fig.legends
    profile['canvas'].update(width_mm=30, aspect_ratio=.6)
    import matplotlib.pyplot as plt
    before = plt.get_fignums()
    with pytest.raises(core.ProfileError, match='Not enough room for a separate legend'):
        core.render_to_svg(spec, profile)
    assert plt.get_fignums() == before


@pytest.mark.parametrize('side',['top','bottom','left','right'])
def test_explicit_sides_keep_legend_outside_axes(side):
    profile=load_default_profile();profile['legend'].update(placement='outside',side=side)
    profile['canvas'].update(width_mm=170,aspect_ratio=110/170)
    spec=json.load(open(case('line-multi')))
    with core.drawn_figure(spec,profile) as (fig,ax,drawn):
        assert drawn['legend_side']==side
        renderer=__import__('inspect_figure').figure_renderer(fig)
        legend=fig.legends[0].get_window_extent(renderer);panel=ax.get_tightbbox(renderer)
        assert {'top':legend.y0>=panel.y1,'bottom':legend.y1<=panel.y0,
                'left':legend.x1<=panel.x0,'right':legend.x0>=panel.x1}[side]
    profile['canvas'].update(width_mm=30,aspect_ratio=.6)
    with pytest.raises(core.ProfileError,match='Not enough room'):
        core.render_to_svg(spec,profile)


def test_side_validation_and_legacy_automatic_position():
    profile=load_default_profile();profile['legend']['placement']='outside'
    for bad in ['diagonal','',None,True]:
        profile['legend']['side']=bad
        with pytest.raises(core.ProfileError,match='legend.side'):
            core.validate_profile(profile)
    del profile['legend']['side']
    spec=json.load(open(case('line-multi')))
    with core.drawn_figure(spec,profile) as (_,_,drawn):
        assert drawn['legend_side']=='right'
