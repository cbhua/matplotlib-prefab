#!/usr/bin/env python3
"""Freeze Matplotlib's unhinted glyph geometry for the demo's fixed text repertoire.

This builds reusable text shapes, not chart positions; all sizing/layout stays JS.
It never rebuilds the original chart reference SVGs.
"""
from pathlib import Path
import json, hashlib, xml.etree.ElementTree as ET
import matplotlib
from matplotlib.textpath import TextToPath
from matplotlib.font_manager import FontProperties
from matplotlib.path import Path as MplPath
from matplotlib import _path

ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'web/chart-demo'
manifest=json.loads((folder/'references.json').read_text())
labels=set()
for case in manifest['cases']:
    spec=case['spec']
    labels.update([spec['x_label'],spec['y_label']])
    labels.update(spec.get('categories',[]))
    labels.update(s['name'] for s in spec.get('series',[]))
    tree=ET.parse(folder/case['asset'],parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
    for n in tree.iter():
        if n.tag is ET.Comment and n.text and not n.text.strip().startswith('Created with'):
            labels.add(n.text.strip())
# Include a modest numeric vocabulary so sensible tick adjustments keep working.
labels.update(str(i).replace('-', '−') for i in range(-10,101))
labels.update(f'{i/10:.1f}'.replace('-','−') for i in range(-20,51))
for specfile in (ROOT/'web/public/generated/specs').glob('*.json'):
    spec=json.loads(specfile.read_text())
    labels.update(v for v in [spec.get('title'),spec.get('x_label'),spec.get('y_label')] if v)
    labels.update(spec.get('categories',[]))
    labels.update(s['name'] for s in spec.get('series',[]))
labels.update(chr(i) for i in range(32,127))
labels.update('−×°')
fontfile=Path(matplotlib.get_data_path())/'fonts/ttf/DejaVuSans.ttf'
prop=FontProperties(fname=str(fontfile),size=100)
ttp=TextToPath();font=ttp._get_font(prop)
shapes={}
for text in sorted(labels):
    verts,codes=ttp.get_text_path(prop,text,False)
    path=MplPath(verts,codes)
    d=_path.convert_to_string(path,None,None,False,None,6,[b'M',b'L',b'Q',b'C',b'z'],False).decode()
    width,height,descent=ttp.get_text_width_height_descent(text,prop,False)
    shapes[text]={'path':d,'width':width,'height':height,'descent':descent}
# Reference "lp" metric is what Matplotlib Text uses to preserve line spacing.
w,h,d=ttp.get_text_width_height_descent('lp',prop,False)
from fontTools.ttLib import TTFont
from matplotlib.markers import MarkerStyle
tt=TTFont(fontfile);units=tt['head'].unitsPerEm
markers={}
for symbol in ['o','s','^','D','v','P']:
    m=MarkerStyle(symbol);path=m.get_path().transformed(m.get_transform())
    markers[symbol]=_path.convert_to_string(path,None,None,False,None,6,[b'M',b'L',b'Q',b'C',b'z'],False).decode()
result={'markers':markers,'font_metrics':{'ascent':tt['OS/2'].sTypoAscender/units,'descent':-tt['OS/2'].sTypoDescender/units},'units_per_em':100,'font':'DejaVu Sans','weight':'normal','matplotlib':matplotlib.__version__,
        'font_sha256':hashlib.sha256(fontfile.read_bytes()).hexdigest(),
        'note':'Unhinted TextToPath outlines and metrics for fixed demo labels/ticks. No chart geometry included.',
        'line_metrics':{'height':h,'descent':d},'shapes':shapes}
variants={}
for weight in ['medium','semibold','bold']:
    from matplotlib.font_manager import findfont
    wp=FontProperties(fname=findfont(FontProperties(family='DejaVu Sans',weight=weight)),size=100)
    runs={}
    for text in sorted(labels):
        verts,codes=ttp.get_text_path(wp,text,False)
        path=MplPath(verts,codes)
        d=_path.convert_to_string(path,None,None,False,None,6,[b'M',b'L',b'Q',b'C',b'z'],False).decode()
        width,height,descent=ttp.get_text_width_height_descent(text,wp,False)
        runs[text]={'path':d,'width':width,'height':height,'descent':descent}
    variants[weight]=runs
result['weights']=variants
result['kerning']={}
from matplotlib.ft2font import Kerning
for weight in ['normal','medium','semibold','bold']:
    from matplotlib.font_manager import findfont
    fp=FontProperties(fname=findfont(FontProperties(family='DejaVu Sans',weight=weight)),size=100)
    face=ttp._get_font(fp)
    chars=[chr(i) for i in range(32,127)] + list('−×°')
    result['kerning'][weight]={a+b:face.get_kerning(face.get_char_index(ord(a)),face.get_char_index(ord(b)),Kerning.UNFITTED)/64 for a in chars for b in chars if face.get_kerning(face.get_char_index(ord(a)),face.get_char_index(ord(b)),Kerning.UNFITTED)}
(folder/'text-outlines.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
print(f'Built {len(shapes)} text outlines; {len((folder/"text-outlines.json").read_bytes())} bytes.')
