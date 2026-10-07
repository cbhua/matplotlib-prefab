"""The exported scatter spec remains reproducible by the Python renderer."""
import json
from pathlib import Path
import figure_core
from conftest import REPO_ROOT,SKILL_ROOT
from helpers import load_default_profile

def test_scatter_preserves_all_points_and_has_no_connecting_lines():
    spec=json.loads((Path(REPO_ROOT)/'tests/data/scatter.json').read_text())
    spec=figure_core.validate_spec(spec);profile=load_default_profile()
    template=figure_core.load_template('scatter',SKILL_ROOT)
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots()
    try:
        template.draw(ax,spec,profile)
        assert len(ax.lines)==2
        for line,series in zip(ax.lines,spec['series']):
            assert line.get_linestyle()=='None'
            assert list(line.get_xdata())==spec['x']
            assert list(line.get_ydata())==series['y']
            assert line.get_markevery()==1
    finally:plt.close(fig)
    result=figure_core.render_to_svg(spec,profile,SKILL_ROOT,checks=True)
    assert result['report']['counts']['fail']==0
