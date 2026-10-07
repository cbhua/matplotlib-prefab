import {renderNativeChart,inspectNativeChart} from './native-chart.js';
const el=id=>document.getElementById(id);
let outlines, manifest, selected, profile, output, pending=false, fontBase64;
const blobs=new Map();
function configKey(p){return JSON.stringify([p.canvas,p.fonts,p.lines,p.bar]);}
function updateView(){
  const matched=configKey(profile)===configKey(selected.profile);
  el('mismatch').hidden=matched;
  for(const o of el('view').options)if(['overlay','difference'].includes(o.value))o.disabled=!matched;
  if(!matched&&['overlay','difference'].includes(el('view').value))el('view').value='side';
  const view=el('view').value;
  el('stage').className=['overlay','difference'].includes(view)?`overlay ${view}`:'';
  el('reference-figure').hidden=view==='native';
  window.__chartDemo.matched=matched;
}
function render(){
  pending=false; const started=performance.now();
  for(const id of ['width','height','type','line-width'])if(!el(id).value||!el(id).checkValidity()){
    el('error').textContent='Enter a value within the displayed control range. Previous chart retained.';el('error').hidden=false;el('download').disabled=true;window.__chartDemo.busy=false;return;
  }
  const next=structuredClone(selected.profile);
  next.canvas.width_mm=Number(el('width').value);next.canvas.aspect_ratio=Number(el('height').value)/next.canvas.width_mm;
  const size=Number(el('type').value);Object.assign(next.fonts,{size_tick_pt:size,size_legend_pt:size,size_axis_label_pt:size+1});
  next.lines.data_linewidth_pt=Number(el('line-width').value);next.lines.markers_enabled=el('markers').checked;
  next.bar.category_label_rotation_deg=Number(el('rotation').value);
  try{
    output=renderNativeChart(selected.spec,next,{outlines:el('text-mode').value==='outlines'?outlines:null});profile=next;el('native').replaceChildren(output.svg);
    const warnings=inspectNativeChart(output.svg);el('warnings').textContent=warnings.join(' ');
    const duration=performance.now()-started;
    el('status').textContent=`${selected.spec.kind} · ${next.canvas.width_mm.toFixed(2)} × ${(next.canvas.width_mm*next.canvas.aspect_ratio).toFixed(2)} mm · ${duration.toFixed(1)} ms browser draw`;
    Object.assign(window.__chartDemo,{profile,spec:selected.spec,geometry:output.geometry,durationMs:duration,warnings});
    el('error').hidden=true;el('download').disabled=false;updateView();
  }catch(error){el('error').textContent=error.message;el('error').hidden=false;el('download').disabled=true;}
  window.__chartDemo.busy=false;
}
function schedule(){window.__chartDemo.busy=true;if(!pending){pending=true;requestAnimationFrame(render);}}
function reset(){
  selected=manifest.cases.find(c=>c.id===el('case').value);const p=selected.profile;
  el('width').value=p.canvas.width_mm;el('height').value=p.canvas.width_mm*p.canvas.aspect_ratio;el('height-slider').value=el('height').value;
  el('type').value=p.fonts.size_tick_pt;el('line-width').value=p.lines.data_linewidth_pt;el('markers').checked=p.lines.markers_enabled;
  el('rotation').value=p.bar.category_label_rotation_deg;el('rotation').disabled=selected.spec.kind!=='bar';
  el('markers').disabled=selected.spec.kind!=='line';el('line-width').disabled=selected.spec.kind!=='line';
  const img=new Image();img.src=blobs.get(selected.id);img.alt=`Matplotlib ${selected.label}`;
  img.style.width=`${p.canvas.width_mm}mm`;img.style.height=`${p.canvas.width_mm*p.canvas.aspect_ratio}mm`;
  el('reference').replaceChildren(img);schedule();
}
function exportedSvg(){
  const clone=output.svg.cloneNode(true);
  if(!clone.querySelector('text'))return new XMLSerializer().serializeToString(clone);
  const style=document.createElementNS('http://www.w3.org/2000/svg','style');
  style.textContent=`@font-face{font-family:'Chart Demo Sans';src:url(data:font/woff2;base64,${fontBase64}) format('woff2');font-weight:400;font-style:normal;}`;
  clone.prepend(style);return new XMLSerializer().serializeToString(clone);
}
try{
  manifest=await fetch('./chart-demo/references.json').then(r=>{if(!r.ok)throw Error('Build demo references first');return r.json();});
  outlines=await fetch('./chart-demo/text-outlines.json').then(r=>{if(!r.ok)throw Error('Missing text outline atlas');return r.json();});
  const font=await fetch('./chart-demo/DejaVuSans.woff2').then(r=>r.arrayBuffer());
  fontBase64=btoa(Array.from(new Uint8Array(font),v=>String.fromCharCode(v)).join(''));
  await Promise.all(manifest.cases.map(async c=>{
    const r=await fetch(`./chart-demo/${c.asset}`);if(!r.ok)throw Error(`Missing reference ${c.id}`);
    blobs.set(c.id,URL.createObjectURL(await r.blob()));
  }));
  for(const c of manifest.cases){const o=document.createElement('option');o.value=c.id;o.textContent=c.label;el('case').append(o);}
  await document.fonts.load('10px "Chart Demo Sans"');
  window.__chartDemo={busy:true,exportedSvg};
  el('versions').textContent=`Frozen reference: Matplotlib ${manifest.environment.matplotlib}, Python ${manifest.environment.python}. Both versions use the packaged DejaVu Sans font.`;
  el('text-mode').addEventListener('change',schedule);
  el('case').addEventListener('change',reset);el('reset').addEventListener('click',reset);el('view').addEventListener('change',updateView);
  for(const id of ['width','height','type','line-width','markers','rotation'])el(id).addEventListener('input',()=>{el('height-slider').value=el('height').value;schedule();});
  el('height-slider').addEventListener('input',()=>{el('height').value=el('height-slider').value;schedule();});
  el('download').addEventListener('click',()=>{
    const url=URL.createObjectURL(new Blob([exportedSvg()],{type:'image/svg+xml'}));const a=document.createElement('a');a.href=url;a.download=`browser-${selected.spec.kind}.svg`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  reset();window.__ready=true;
}catch(error){el('error').hidden=false;el('error').textContent=String(error);window.__chartDemoError=String(error);}
