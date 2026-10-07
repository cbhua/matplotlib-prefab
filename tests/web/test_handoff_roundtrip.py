"""The actual browser handoff remains consumable by the bundled Python skill."""
import json
from pathlib import Path
import pytest
import import_handoff
import render
from pypdf import PdfReader
from conftest import needs_browser,needs_fonts,REPO_ROOT
from lab import open_lab
pytestmark=[needs_browser,needs_fonts]


@pytest.mark.parametrize('mixed',[False,True])
def test_copy_import_render_preserves_dimensions_and_data(tmp_path,mixed):
    with open_lab() as lab:
        p=lab.page
        if mixed:
            p.wait_for_selector('[data-venue="icml2026"]')
            p.click('[data-venue="icml2026"]');p.click('[data-grid="1x2"]')
            p.click('[data-layout="wide"]');p.click('#setup-next')
        lab.wait_ready();lab.wait_for_render()
        if mixed:
            imported=json.loads((Path(REPO_ROOT)/'tests/data/scatter.json').read_text())
            p.select_option('#active-panel','1')
            p.set_input_files('#spec-file',{'name':'measurements.json','mimeType':'application/json','buffer':json.dumps(imported).encode()})
            p.wait_for_function("window.__lab.currentSpec.panels[1].kind==='scatter'")
            lab.wait_for_render()
        bundle=lab.export_bundle()
        extracted=import_handoff.extract_handoff(lab.export_text())
    assert extracted['spec']==bundle['spec']
    assert extracted['profile']==bundle['profile']
    assert extracted['metadata']['data_usage']['intent']==('preserve-supplied-data' if mixed else 'style-reference')
    import_handoff.write_handoff(extracted,tmp_path/'input')
    report=render.render(str(tmp_path/'input/spec.json'),str(tmp_path/'output'),str(tmp_path/'input/profile.json'))
    assert report['status']!='fail'
    output=json.loads((tmp_path/'output/spec.json').read_text())
    assert output==bundle['spec']
    rect=PdfReader(tmp_path/'output/figure.pdf').pages[0].mediabox
    assert float(rect.width)*25.4/72==pytest.approx(bundle['profile']['canvas']['width_mm'],abs=.001)
    assert float(rect.height)*25.4/72==pytest.approx(bundle['target']['figure_height_mm'],abs=.001)
