#!/usr/bin/env python3
"""Compare native SVG plot bounds with frozen Matplotlib references; save review PNGs."""
import sys,json,re,os,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0,str(ROOT/'tests/web'))
from lab import browser_runtime
from server import static_server
cases=json.loads(Path('web/chart-demo/references.json').read_text())['cases'];rows=[]
with static_server('web') as origin,browser_runtime() as p:
 b=p.chromium.launch();page=b.new_page(viewport={'width':1600,'height':1100},device_scale_factor=2)
 page.goto(origin+'/chart-demo.html');page.wait_for_function('window.__chartDemo && !window.__chartDemo.busy')
 for case in cases:
  page.select_option('#case',case['id']);page.wait_for_function('!window.__chartDemo.busy')
  page.locator('#reference img').evaluate('(n)=>n.decode()')
  g=page.evaluate('window.__chartDemo.geometry')
  xml=ET.parse('web/chart-demo/'+case['asset']);path=next(n for n in xml.iter() if n.get('id')=='patch_2')[0].get('d')
  points=list(map(float,re.findall(r'-?\d+(?:\.\d+)?',path)))
  ref=dict(left=points[0],bottom=points[1],right=points[2],top=points[5])
  delta={k:abs(g[k]-v)*25.4/72 for k,v in ref.items()}
  row={'case':case['id'],'plot_edge_error_mm':delta,'warnings':page.evaluate('window.__chartDemo.warnings'),'draw_ms':page.evaluate('window.__chartDemo.durationMs')};rows.append(row)
  folder=Path('.tmp/native-chart');folder.mkdir(exist_ok=True,parents=True)
  page.locator('#native svg').screenshot(path=str(folder/(case['id']+'-native.png')))
  page.locator('#reference img').screenshot(path=str(folder/(case['id']+'-matplotlib.png')))
 print(json.dumps(rows,indent=2))
 Path('.tmp/native-chart/report.json').write_text(json.dumps(rows,indent=2)+'\n')
 b.close()
