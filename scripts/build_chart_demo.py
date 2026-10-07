#!/usr/bin/env python3
"""Offline-only Matplotlib references for the standalone native-SVG demo."""
from pathlib import Path
import sys, json, hashlib, shutil
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'web'))
import figure_backend
from fontTools.ttLib import TTFont
import matplotlib

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    out=ROOT/'web/chart-demo'; out.mkdir(exist_ok=True)
    profile=json.loads((ROOT/'web/public/generated/profiles/single-column.json').read_text())
    fontdir=Path(matplotlib.get_data_path())/'fonts/ttf'
    font=TTFont(fontdir/'DejaVuSans.ttf');font.flavor='woff2';font.save(out/'DejaVuSans.woff2')
    shutil.copyfile(fontdir/'LICENSE_DEJAVU',out/'LICENSE_DEJAVU.txt')
    cases=[]
    for kind, name in [('line','line-multi'),('bar','bar-signed')]:
        spec=json.loads((ROOT/f'web/public/generated/specs/{name}.json').read_text())
        for variant,width,height,size,weight in [('default',82.55,51.0159,8,1.2),('tall',82.55,90,8,1.2),('wide',139.7,60,8,1.2),('large-type',100,65,11,1.2),('thick-lines',82.55,51.0159,8,2.4)]:
            p=json.loads(json.dumps(profile));p['canvas'].update(width_mm=width,aspect_ratio=height/width)
            p['fonts'].update(size_tick_pt=size,size_axis_label_pt=size+1,size_legend_pt=size)
            p['lines']['data_linewidth_pt']=weight
            result=figure_backend.render({'spec':spec,'profile':p})
            if not result['ok']: raise RuntimeError(result)
            id=f'{kind}-{variant}';path=out/f'{id}.svg';path.write_text(result['svg'])
            cases.append({'id':id,'label':f'{kind.title()} · {variant}', 'spec':spec,'profile':p,
                          'asset':f'{id}.svg','sha256':sha(path)})
    manifest={'note':'Frozen Matplotlib references generated offline. The browser renderer uses spec/profile only, never reference geometry.',
              'environment':figure_backend.environment(),'font_sha256':sha(out/'DejaVuSans.woff2'),
              'sources':{str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'skills/scientific-figures/scripts/figure_core.py',ROOT/'skills/scientific-figures/assets/templates/line.py',ROOT/'skills/scientific-figures/assets/templates/bar.py']},'cases':cases}
    (out/'references.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'Built {len(cases)} reference SVGs and the matching DejaVu font.')
if __name__=='__main__':main()
