/** Main-tool renderer. Static glyph assets; no Python runtime or render API. */
import {renderNativeChart} from './native-chart.js';
import {validateFigureSpec} from './spec-validation.js';
import {evaluateFigure} from './figure-checks.js';
const NS='http://www.w3.org/2000/svg';
function validateProfile(profile) {
  const fail=message=>{const e=new Error(message);e.name='ProfileError';throw e;};
  for(const section of ['canvas','fonts','lines','axes','bar','legend','layout','colors'])if(!profile?.[section])fail(`Missing profile.${section}`);
  for(const [section,fields] of Object.entries(profile))if(fields&&typeof fields==='object')for(const [key,value] of Object.entries(fields)){
    if(typeof value==='number'&&!Number.isFinite(value))fail(`${section}.${key} must be finite`);
    if(section==='fonts'&&key.startsWith('size_')&&(!(value>0)||typeof value!=='number'))fail(`${section}.${key} must be strictly positive`);
    if(section==='fonts'&&key.startsWith('weight')&&!['normal','medium','semibold','bold'].includes(value))fail(`Unsupported font weight: ${value}`);
  }
  for(const [section,keys] of Object.entries({lines:['data_linewidth_pt','axes_linewidth_pt','tick_linewidth_pt','tick_length_pt','tick_pad_pt','marker_size_pt'],axes:['margin_x','margin_y','grid_alpha','grid_linewidth_pt'],bar:['edge_linewidth_pt','zero_line_linewidth_pt'],layout:['pad_pt']}))
    for(const key of keys)if(!(profile[section][key]>=0))fail(`${section}.${key} must be nonnegative`);
  for(const [section,key] of [['axes','max_xticks'],['axes','max_yticks'],['lines','max_markers_per_series']])if(!Number.isInteger(profile[section][key])||profile[section][key]<2||profile[section][key]>100)fail(`${section}.${key} must be an integer from 2 to 100`);
  if(!(profile.bar.width_fraction>0&&profile.bar.width_fraction<=1))fail('bar.width_fraction must be in (0, 1]');
}
export function outlineRenderer(base) {
  let atlas, stopped=false;
  const listeners=new Set();
  const emit=data=>{if(!stopped){adapter.onmessage?.({data});for(const fn of listeners)fn({data});}};
  const adapter={onmessage:null,terminate(){stopped=true;listeners.clear();},
    addEventListener(type,fn){if(type==='message')listeners.add(fn);},
    removeEventListener(type,fn){listeners.delete(fn);},
    async postMessage(job){
      if(job.type==='boot'){
        try {const r=await fetch(`${base}chart-demo/text-outlines.json`);if(!r.ok)throw Error('Could not load outline assets');atlas=await r.json();
          emit({type:'ready',stats:{backend:'svg-outlines',total_ms:0,environment:{renderer:'browser.svg-outlines',version:'0.5.0',outline_matplotlib:atlas.matplotlib,font_sha256:atlas.font_sha256}}});
        }catch(e){emit({type:'fatal',error:e.message});}return;
      }
      if(job.type!=='render')return;
      queueMicrotask(()=>{
        const started=performance.now();let result;
        try {
          const {spec,profile}=job;validateProfile(profile);validateFigureSpec(spec);
          const width=profile.canvas.width_mm,height=width*profile.canvas.aspect_ratio;
          if(!Number.isFinite(width+height)||width<=0||height<=0)throw Error('Figure dimensions must be positive.');
          const panels=spec.kind==='grid'?spec.panels:[spec],rows=spec.kind==='grid'?spec.rows:1,cols=spec.kind==='grid'?spec.columns:1;
          if(!Number.isInteger(rows)||!Number.isInteger(cols)||rows<1||cols<1||rows>4||cols>4||panels.length!==rows*cols)throw Error('Invalid panel grid.');
          const svg=document.createElementNS(NS,'svg');
          for(const [k,v] of Object.entries({xmlns:NS,width:`${width}mm`,height:`${height}mm`,viewBox:`0 0 ${width*72/25.4} ${height*72/25.4}`,role:'img','aria-label':'Scientific figure'}))svg.setAttribute(k,v);
          const warnings=[],drawn=[];
          const host=document.createElement('div');host.style.cssText='position:absolute;left:-10000px;top:0;visibility:hidden';document.body.append(host);host.append(svg);
          try {panels.forEach((panel,i)=>{
            const p=structuredClone(profile);p.canvas.width_mm=width/cols;p.canvas.aspect_ratio=(height/rows)/(width/cols);
            const chart=renderNativeChart(panel,p,{outlines:atlas});
            host.append(chart.svg);
            warnings.push(...evaluateFigure(chart.svg,i,p,chart.geometry));
            const group=document.createElementNS(NS,'g');group.setAttribute('class','figure-panel');group.setAttribute('transform',`translate(${(i%cols)*width/cols*72/25.4} ${Math.floor(i/cols)*height/rows*72/25.4})`);
            for(const attr of ['fill','font-family'])group.setAttribute(attr,chart.svg.getAttribute(attr));
            group.append(...chart.svg.childNodes);chart.svg.remove();svg.append(group);
            drawn.push({kind:panel.kind,geometry:chart.geometry});
          });} finally {host.remove();}
          const checks=[{id:'renderer',status:'pass',message:'Browser SVG with offline Matplotlib text outlines.'},...warnings,{id:'visual_review',status:'not_checked',message:'Inspect the figure at its intended print size.'}];
          result={ok:true,svg:new XMLSerializer().serializeToString(svg),width_mm:width,height_mm:height,width_in:width/25.4,height_in:height/25.4,
            resolved_spec:structuredClone(spec),resolved_profile:structuredClone(profile),drawn:{kind:spec.kind,panels:drawn},
            report:{mode:'browser-svg',status:warnings.length?'warn':'pass',checks,counts:{pass:1,warn:warnings.length,fail:0,not_checked:1}},render_ms:performance.now()-started};
        }catch(e){result={ok:false,error:e.message,error_kind:e.name==='ProfileError'?'ProfileError':'SpecError'};}
        emit({type:'render-result',id:job.id,result,wall_ms:performance.now()-started});
      });
    }};
  return adapter;
}
