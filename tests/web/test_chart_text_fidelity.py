"""Isolate actual reference text at identical baselines; compare glyph ink, not whitespace."""
from pathlib import Path
import io, json
import numpy as np
from PIL import Image
import pytest
from conftest import needs_browser, REPO_ROOT
from lab import browser_runtime
from server import static_server

pytestmark=[needs_browser]
ROOT=Path(REPO_ROOT)

@pytest.mark.parametrize('dpr',[1,2,3])
def test_matplotlib_glyph_ink_matches_without_font_rendering(dpr):
    report=[]
    with static_server(str(ROOT/'web')) as origin,browser_runtime() as runtime:
        browser=runtime.chromium.launch()
        page=browser.new_page(viewport={'width':1400,'height':1000},device_scale_factor=dpr)
        page.goto(origin+'/chart-demo.html');page.wait_for_function('window.__chartDemo && !window.__chartDemo.busy')
        for case in ['line-default','line-large-type','bar-default']:
            page.select_option('#case',case);page.wait_for_function('!window.__chartDemo.busy')
            # Read the actual frozen SVG as the independent glyph oracle.
            page.evaluate('''async id=>{
              document.querySelector('#text-probe')?.remove();
              const xml=await fetch(`./chart-demo/${id}.svg`).then(r=>r.text());
              const reference=new DOMParser().parseFromString(xml,'image/svg+xml');
              const ns='http://www.w3.org/2000/svg';
              const host=document.createElement('div');host.id='text-probe';
              Object.assign(host.style,{position:'absolute',left:'0',top:'0',background:'white',zIndex:10000});
              const original=document.querySelector('#native .ylabel');
              const value=original.dataset.chartText, size=Number(original.getAttribute('font-size'));
              let refGroup;
              const walker=document.createTreeWalker(reference,NodeFilter.SHOW_COMMENT);
              while(walker.nextNode()) if(walker.currentNode.textContent.trim()===value) {
                refGroup=walker.currentNode.nextSibling;
                while(refGroup?.nodeType!==1)refGroup=refGroup.nextSibling;
                break;
              }
              if(!refGroup)throw Error('Missing reference text');
              for(const mode of ['reference','outlines','browser']){
                const svg=document.createElementNS(ns,'svg');svg.id=`probe-${mode}`;
                svg.setAttribute('width','400');svg.setAttribute('height','80');svg.setAttribute('viewBox','0 0 300 60');
                svg.style.display='block';svg.style.background='white';
                if(mode==='reference'){
                  for(const d of reference.querySelectorAll('defs'))svg.append(d.cloneNode(true));
                  const g=refGroup.cloneNode(true);g.setAttribute('transform',`translate(16 32) scale(${size/100} ${-size/100})`);svg.append(g);
                }else if(mode==='outlines'){
                  const p=original.querySelector('path').cloneNode(true);p.setAttribute('transform',`translate(16 32) scale(${size/100} ${-size/100})`);svg.append(p);
                }else{
                  const t=document.createElementNS(ns,'text');t.setAttribute('x','16');t.setAttribute('y','32');
                  t.setAttribute('font-size',size);t.setAttribute('font-family','Chart Demo Sans');t.textContent=value;svg.append(t);
                }
                host.append(svg);
              }
              document.body.append(host);
            }''',case)
            rasters={mode:np.asarray(Image.open(io.BytesIO(page.locator('#probe-'+mode).screenshot())).convert('L'),dtype=float) for mode in ['reference','outlines','browser']}
            ref=rasters['reference'];ink=np.sum(255-ref)
            row={'case':case,'dpr':dpr}
            for mode in ['outlines','browser']:
                row[mode]={'ink_difference':float(np.abs(ref-rasters[mode]).sum()/ink),
                           'ink_mass_ratio':float((255-rasters[mode]).sum()/ink)}
            assert row['outlines']['ink_difference'] < .01, row
            assert abs(row['outlines']['ink_mass_ratio']-1)<.005,row
            assert row['outlines']['ink_difference'] <= row['browser']['ink_difference']+.001,row
            report.append(row)
        browser.close()
    folder=ROOT/'.tmp/native-chart';folder.mkdir(exist_ok=True,parents=True)
    (folder/f'text-fidelity-dpr{dpr}.json').write_text(json.dumps(report,indent=2)+'\n')
