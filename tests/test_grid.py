"""Grid output keeps every panel's data and physical typography at export size."""
import copy
import json
from pathlib import Path

import pytest
import figure_core
import grid_core
import render

ROOT = Path(__file__).resolve().parents[1]


def inputs(rows=2, columns=2):
    panels = [json.loads((ROOT / 'tests/data' / name).read_text())
              for name in ('line-multi.json', 'bar-positive.json')]
    spec = {'schema_version': '1', 'kind': 'grid', 'rows': rows, 'columns': columns,
            'panels': [copy.deepcopy(panels[i % 2]) for i in range(rows * columns)]}
    profile = figure_core.load_profile(str(ROOT / 'skills/scientific-figures/references/profiles/single-column.json'))
    profile['canvas']['width_mm'] = 171.45
    return spec, profile


@pytest.mark.parametrize('rows,columns', [(1, 2), (1, 3), (1, 4), (2, 1), (2, 2), (4, 4)])
def test_grid_preserves_data_size_and_type(rows, columns):
    spec, profile = inputs(rows, columns)
    result = grid_core.render_to_svg(spec, profile, checks=True)
    assert result['spec'] == spec
    assert result['width_mm'] == pytest.approx(171.45)
    assert result['height_mm'] == pytest.approx(171.45 * .618)
    assert len(result['drawn']['panels']) == rows * columns
    assert not [c for c in result['report']['checks'] if c['status'] == 'fail']
    assert all(c['status'] == 'pass' for c in result['report']['checks'] if c['id'].endswith('font_sizes'))


@pytest.mark.parametrize('change,field', [({'rows': 0}, 'rows'), ({'columns': True}, 'columns'),
                                        ({'rows': 5}, 'rows'), ({'panels': []}, 'panels'),
                                        ({'unknown': 1}, 'unknown')])
def test_invalid_grid_is_rejected(change, field):
    spec, _ = inputs()
    spec.update(change)
    with pytest.raises(figure_core.SpecError, match=field):
        grid_core.validate_spec(spec)


def test_error_names_the_bad_panel():
    spec, _ = inputs()
    spec['panels'][1]['values'] = [True]
    with pytest.raises(figure_core.SpecError, match=r'panels\[1\]'):
        grid_core.validate_spec(spec)


def test_grid_cli_exports_reproducible_files(tmp_path):
    spec, profile = inputs()
    source, style = tmp_path / 'input.json', tmp_path / 'style.json'
    source.write_text(json.dumps(spec))
    style.write_text(json.dumps(profile))
    output = tmp_path / 'out'
    report = render.render(str(source), str(output), str(style))
    assert {p.name for p in output.iterdir()} == set(figure_core.MANAGED_OUTPUTS)
    assert json.loads((output / 'spec.json').read_text()) == spec
    assert report['status'] != 'fail'
    from pypdf import PdfReader
    assert float(PdfReader(output / 'figure.pdf').pages[0].mediabox.width) == pytest.approx(171.45 / 25.4 * 72)
