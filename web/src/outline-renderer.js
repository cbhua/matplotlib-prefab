/** Main-tool renderer. Static glyph assets; no Python runtime or render API. */
import {renderNativeChart} from './native-chart.js';
import {validateFigureSpec} from './spec-validation.js';
import {evaluateFigure} from './figure-checks.js';
import {measureVisualDensity,VISUAL_DENSITY_RULES} from './visual-density.js';
import {renderOutsideLegend} from './outside-legend.js';
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
  if(!['inside','outside'].includes(profile.legend.placement??'inside'))fail('legend.placement must be inside or outside');
  if(!['auto','top','bottom','left','right'].includes(profile.legend.side??'auto'))fail('legend.side must be top, bottom, left, right or auto');
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
      queueMicrotask(async ()=>{
        const started=performance.now();let result;
        try {
          const {spec,profile}=job;validateProfile(profile);validateFigureSpec(spec);
          const width=profile.canvas.width_mm,height=width*profile.canvas.aspect_ratio;
          if(!Number.isFinite(width+height)||width<=0||height<=0)throw Error('Figure dimensions must be positive.');
          const panels=spec.kind==='grid'?spec.panels:[spec],rows=spec.kind==='grid'?spec.rows:1,cols=spec.kind==='grid'?spec.columns:1;
          if(!Number.isInteger(rows)||!Number.isInteger(cols)||rows<1||cols<1||rows>4||cols>4||panels.length!==rows*cols)throw Error('Invalid panel grid.');
          const svg=document.createElementNS(NS,'svg');
          for(const [k,v] of Object.entries({xmlns:NS,width:`${width}mm`,height:`${height}mm`,viewBox:`0 0 ${width*72/25.4} ${height*72/25.4}`,role:'img','aria-label':'Scientific figure'}))svg.setAttribute(k,v);
          const warnings=[],drawn=[],densityPanels=[];
          const outside=profile.legend.placement==='outside'?renderOutsideLegend(spec,profile,atlas):null;
          const pt=72/25.4,pad=profile.layout.pad_pt;
          const gap=outside?Math.max(6,profile.fonts.size_legend_pt):0;
          const chartsFor=(w,h)=>panels.map(panel=>{
            const p=structuredClone(profile);p.canvas.width_mm=w/pt/cols;p.canvas.aspect_ratio=(h/pt/rows)/p.canvas.width_mm;
            return {p,chart:renderNativeChart(panel,p,{outlines:atlas,hideLegend:Boolean(outside)})};
          });
          let plotWidth=width*pt,plotHeight=height*pt,charts,legendLayout;
          if(outside){
            const w=width*pt,h=height*pt;
            const layouts={
              right:{side:'right',w:w-outside.width-gap-pad,h,x:w-outside.width-pad,y:(h-outside.height)/2,dx:0,dy:0},
              left:{side:'left',w:w-outside.width-gap-pad,h,x:pad,y:(h-outside.height)/2,dx:outside.width+gap+pad,dy:0},
              bottom:{side:'bottom',w,h:h-outside.height-gap-pad,x:(w-outside.width)/2,y:h-outside.height-pad,dx:0,dy:0},
              top:{side:'top',w,h:h-outside.height-gap-pad,x:(w-outside.width)/2,y:pad,dx:0,dy:outside.height+gap+pad},
            };
            const requested=profile.legend.side??'auto';
            const candidates=requested==='auto'?[layouts.right,layouts.bottom]:[layouts[requested]];
            for(const c of candidates){
              if(c.w<=0||c.h<=0||c.x<pad||c.y<pad)continue;
              try{charts=chartsFor(c.w,c.h);plotWidth=c.w;plotHeight=c.h;legendLayout=c;break;}
              catch(error){if(!error.message.startsWith('Not enough room'))throw error;}
            }
            if(!legendLayout)throw Error('Not enough room for a separate legend. Increase the figure width or height, or reduce the legend size.');
          }else charts=chartsFor(plotWidth,plotHeight);
          if(outside){
            const background=document.createElementNS(NS,'rect');
            for(const [k,v] of Object.entries({width:width*pt,height:height*pt,fill:profile.canvas.background}))background.setAttribute(k,v);
            svg.append(background);
          }
          const host=document.createElement('div');host.style.cssText='position:absolute;left:-10000px;top:0;visibility:hidden';document.body.append(host);host.append(svg);
          try {for(const [i,panel] of panels.entries()){
            const {p,chart}=charts[i];
            host.append(chart.svg);
            const density=await measureVisualDensity(chart.svg,chart.geometry);
            densityPanels.push({panel_index:i,kind:panel.kind,...density});
            warnings.push(...evaluateFigure(chart.svg,i,p,chart.geometry,density));
            const group=document.createElementNS(NS,'g');group.setAttribute('class','figure-panel');group.setAttribute('transform',`translate(${(legendLayout?.dx??0)+(i%cols)*plotWidth/cols} ${(legendLayout?.dy??0)+Math.floor(i/cols)*plotHeight/rows})`);
            for(const attr of ['fill','font-family'])group.setAttribute(attr,chart.svg.getAttribute(attr));
            group.append(...chart.svg.childNodes);chart.svg.remove();svg.append(group);
            drawn.push({kind:panel.kind,geometry:chart.geometry});
          }
          if(outside){
            const group=document.createElementNS(NS,'g');group.setAttribute('class','figure-legend');
            group.setAttribute('transform',`translate(${legendLayout.x} ${legendLayout.y})`);
            group.dataset.side=legendLayout.side;
            group.setAttribute('fill',outside.svg.getAttribute('fill'));
            group.append(...outside.svg.childNodes);svg.append(group);
          }} finally {host.remove();}
          const checks=[...densityPanels.filter(p=>p.ink.status==='not_checked').map(p=>({id:`panel_${p.panel_index+1}.density_raster`,status:'not_checked',message:p.ink.reason})),{id:'renderer',status:'pass',message:'Browser SVG with offline Matplotlib text outlines.'},...warnings,{id:'visual_review',status:'not_checked',message:'Inspect the figure at its intended print size.'}];
          result={ok:true,svg:new XMLSerializer().serializeToString(svg),width_mm:width,height_mm:height,width_in:width/25.4,height_in:height/25.4,
            resolved_spec:structuredClone(spec),resolved_profile:structuredClone(profile),drawn:{kind:spec.kind,panels:drawn,...(outside?{legend:{placement:'outside',side:legendLayout.side,entries:outside.entries}}:{})},
            report:{visual_density:{method:'print-space-ink-occupancy-overdraw',rules:VISUAL_DENSITY_RULES,panels:densityPanels},mode:'browser-svg',status:warnings.length?'warn':'pass',checks,counts:{pass:1,warn:warnings.length,fail:0,not_checked:checks.filter(c=>c.status==='not_checked').length}},render_ms:performance.now()-started};
        }catch(e){result={ok:false,error:e.message,error_kind:e.name==='ProfileError'?'ProfileError':'SpecError'};}
        emit({type:'render-result',id:job.id,result,wall_ms:performance.now()-started});
      });
    }};
  return adapter;
}
