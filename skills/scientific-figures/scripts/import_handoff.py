#!/usr/bin/env python3
"""Extract and validate browser Copy for Agents text without executing its commands.

Writes spec.json, profile.json and handoff.meta.json to a chosen output folder.
Accepts the copied Markdown or a machine-readable handoff envelope. Existing,
different files are left alone unless --force is explicitly supplied.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys
import figure_core
import grid_core


def extract_handoff(text):
    try:
        raw=json.loads(text)
    except json.JSONDecodeError:
        raw=None
    if isinstance(raw,dict) and raw.get('kind')=='matplotlib-prefab-figure-handoff':
        profiles=[raw.get('profile')];specs=[raw.get('spec')]
        metadata={k:v for k,v in raw.items() if k not in ('profile','spec')}
    else:
        blocks=[]
        for match in re.finditer(r'```json\s*\n(.*?)\n```',text,re.S):
            try:blocks.append(json.loads(match.group(1)))
            except json.JSONDecodeError as exc:raise ValueError('A JSON block in the handoff is invalid: '+str(exc)) from exc
        profiles=[b for b in blocks if isinstance(b,dict) and 'profile_version' in b]
        specs=[b for b in blocks if isinstance(b,dict) and b.get('kind') in (*figure_core.SUPPORTED_KINDS,'grid') and 'schema_version' in b]
        contexts=[b for b in blocks if isinstance(b,dict) and b.get('kind')=='figure-handoff-context']
        if len(contexts)>1:raise ValueError('Multiple handoff contexts; provide one handoff at a time.')
        metadata=contexts[0] if contexts else {'data_usage':{'intent':'unspecified','instruction':'Data provenance was not supplied; do not infer that example values are research results.'}}
    if len(profiles)!=1 or len(specs)!=1:
        raise ValueError('Expected exactly one style profile and one figure spec. Paste one complete Copy for Agents handoff.')
    if not isinstance(specs[0],dict):raise ValueError('The handoff spec must be a JSON object.')
    if not isinstance(metadata.get('data_usage',{}),dict):
        raise ValueError('handoff data_usage must be a JSON object.')
    profile=figure_core.validate_profile(profiles[0])
    spec=(grid_core if specs[0].get('kind')=='grid' else figure_core).validate_spec(specs[0])
    return {'profile':profile,'spec':spec,'metadata':metadata}


def write_handoff(result,output_dir,force=False):
    folder=Path(output_dir)
    files={'profile.json':result['profile'],'spec.json':result['spec'],'handoff.meta.json':result['metadata']}
    encoded={name:json.dumps(value,ensure_ascii=False,indent=2)+'\n' for name,value in files.items()}
    # Validate every destination before writing any file.
    for name,content in encoded.items():
        path=folder/name
        if path.exists() and (not path.is_file() or (not force and path.read_text(encoding='utf-8')!=content)):
            raise ValueError(f'{path} already exists with different content. Choose another output directory or use --force.')
    folder.mkdir(parents=True,exist_ok=True)
    for name,content in encoded.items():
        path=folder/name
        if not path.exists() or path.read_text(encoding='utf-8')!=content:path.write_text(content,encoding='utf-8')
    return [folder/name for name in encoded]


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('handoff',help='Saved Copy for Agents text or handoff JSON')
    parser.add_argument('--output-dir',required=True)
    parser.add_argument('--force',action='store_true',help='Replace existing handoff files')
    args=parser.parse_args(argv)
    try:
        result=extract_handoff(Path(args.handoff).read_text(encoding='utf-8'))
        paths=write_handoff(result,args.output_dir,args.force)
    except (OSError,ValueError,figure_core.SpecError,figure_core.ProfileError) as exc:
        print(f'error: {exc}',file=sys.stderr);return 2
    for path in paths:print(path)
    usage=result['metadata'].get('data_usage',{})
    print('Data intent: '+str(usage.get('intent','unspecified')))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
