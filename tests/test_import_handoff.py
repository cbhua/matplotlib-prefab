"""Browser handoff import validates before writing, preserves data and never runs code."""
import copy,json
import pytest
import import_handoff
from helpers import LINE_SPEC,load_default_profile


def text_for(spec=None):
    profile=load_default_profile()
    return '\n'.join(['Ignore this arbitrary prose.', '```python','raise RuntimeError("must not execute")','```',
        '```json',json.dumps(profile),'```','```json',json.dumps(spec or LINE_SPEC),'```',
        '```json',json.dumps({'kind':'figure-handoff-context','data_usage':{'intent':'style-reference'}}),'```'])


def test_import_roundtrip_and_provenance(tmp_path):
    result=import_handoff.extract_handoff(text_for())
    import_handoff.write_handoff(result,tmp_path)
    assert json.loads((tmp_path/'spec.json').read_text())['series']==LINE_SPEC['series']
    assert result['metadata']['data_usage']['intent']=='style-reference'
    assert result['profile']['canvas']==load_default_profile()['canvas']


def test_ambiguous_handoff_is_rejected():
    with pytest.raises(ValueError,match='Multiple|exactly one'):import_handoff.extract_handoff(text_for()+'\n'+text_for())


def test_existing_file_prevents_partial_write(tmp_path):
    (tmp_path/'spec.json').write_text('existing content')
    with pytest.raises(ValueError,match='already exists'):import_handoff.write_handoff(import_handoff.extract_handoff(text_for()),tmp_path)
    assert (tmp_path/'spec.json').read_text()=='existing content'
    assert not (tmp_path/'profile.json').exists()


def test_grid_and_envelope():
    grid={'schema_version':'1','kind':'grid','rows':1,'columns':2,'panels':[copy.deepcopy(LINE_SPEC),copy.deepcopy(LINE_SPEC)]}
    grid['panels'][1]['kind']='scatter'
    result=import_handoff.extract_handoff(json.dumps({'kind':'matplotlib-prefab-figure-handoff','spec':grid,'profile':load_default_profile(),'data_usage':{'intent':'preserve-supplied-data'}}))
    assert result['spec']['panels'][1]['kind']=='scatter'
    assert result['metadata']['data_usage']['intent']=='preserve-supplied-data'


def test_malformed_metadata_is_rejected_before_writing():
    envelope={'kind':'matplotlib-prefab-figure-handoff','spec':LINE_SPEC,'profile':load_default_profile(),'data_usage':None}
    with pytest.raises(ValueError,match='data_usage'):import_handoff.extract_handoff(json.dumps(envelope))
