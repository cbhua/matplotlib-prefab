/** Standalone prototype: single-panel fixed-example line/bar charts in SVG.
 * Units in viewBox are points (72/in); never scale type when canvas changes.
 * Layout is computed here; optional offline glyph/marker outlines preserve shape.
 * No network, Python or WASM is consulted by this module.
 */
const NS='http://www.w3.org/2000/svg';
let sequence=0;
function node(tag, attrs={}, text) {
  const n=document.createElementNS(NS,tag);
  for(const [key,value] of Object.entries(attrs)) n.setAttribute(key,String(value));
  if(text!==undefined)n.textContent=text;
  return n;
}
const context=document.createElement('canvas').getContext('2d');
const browserMeasure=(text,size)=>{context.font=`${size}px "Chart Demo Sans"`;return context.measureText(text).width;};
export function ticks(low,high,count) {
  const raw=(high-low)/(count-1), power=10**Math.floor(Math.log10(raw));
  const step=([1,1.5,2,2.5,3,4,5,6,8,10].find(n=>n*power>=raw-1e-10)||10)*power;
  const values=[];
  for(let i=Math.ceil(low/step-1e-9);i<=Math.floor(high/step+1e-9);i++) values.push(Number((i*step).toPrecision(12)));
  const decimals=Math.max(0,-Math.floor(Math.log10(step)) + (String(step).includes('5') && step<1 ? 1:0));
  return values.map(value=>({value,label:value.toFixed(decimals).replace('-','−')}));
}
function marker(shape,x,y,size,color,attrs={}) {
  const r=size/2;
  if(shape==='s')return node('rect',{x:x-r,y:y-r,width:size,height:size,fill:color,...attrs});
  if(shape==='^')return node('path',{d:`M${x},${y-r}L${x+r},${y+r}L${x-r},${y+r}Z`,fill:color,...attrs});
  return node('circle',{cx:x,cy:y,r,fill:color,...attrs});
}
export function renderNativeChart(spec,p,options={}) {
  const atlas=options.outlines;
  let activeWeight='normal';
  const shape=(value,fontWeight=activeWeight)=>{const runs=fontWeight==='normal'?atlas?.shapes:atlas?.weights?.[fontWeight];let result=runs?.[value];
    if(!result && [...value].every(ch=>runs?.[ch]) && runs) {let width=0,height=0,descent=0;const parts=[];let previous='';for(const ch of value){const g=runs[ch];if(!g)break;width+=atlas.kerning?.[fontWeight]?.[previous+ch]||0;previous=ch;parts.push({path:g.path,x:width});width+=g.width;height=Math.max(height,g.height);descent=Math.max(descent,g.descent);}if(parts.length===value.length)result={parts,width,height,descent};}
    if(!result)throw Error(`No outlined glyph run for "${value}". This label contains unsupported characters; rebuild the outline atlas to include it.`);return result;};
  const measure=(value,size,fontWeight='normal')=>atlas?shape(value,fontWeight).width*size/100:browserMeasure(value,size);
  const metrics=(value,size,fontWeight='normal')=>{
    if(!atlas)return {ascent:size*.8,descent:size*.2,height:size};
    const glyph=shape(value,fontWeight);
    const ascent=Math.max(atlas.font_metrics.ascent,(glyph.height-glyph.descent)/100)*size;
    const descent=Math.max(atlas.font_metrics.descent,glyph.descent/100)*size;
    return {ascent,descent,height:ascent+descent};
  };
  const drawMarker=(symbol,x,y,size,color,attrs={})=>atlas
    ?node('path',{d:atlas.markers[symbol],transform:`translate(${x} ${y}) scale(${size} ${-size})`,fill:color,...attrs})
    :marker(symbol,x,y,size,color,attrs);
  if(!['line','bar','scatter'].includes(spec.kind))throw Error('Supported figures: line, bar and scatter.');
  const width=p.canvas.width_mm*72/25.4,height=width*p.canvas.aspect_ratio;
  if(!Number.isFinite(width+height)||width<=0||height<=0)throw Error('Figure dimensions must be positive.');
  const f=p.fonts,l=p.lines,a=p.axes,c=p.colors;
  const weight=role=>f['weight_'+role]??f.weight;
  const tick=f.size_tick_pt,label=f.size_axis_label_pt,legend=f.size_legend_pt,pad=p.layout.pad_pt;
  const xtick=f.size_xtick_pt??tick,ytick=f.size_ytick_pt??tick,xlabel=f.size_x_label_pt??label,ylabel=f.size_y_label_pt??label;
  if(spec.kind!=='bar'&&(!Array.isArray(spec.series)||!spec.series.length))throw Error('A line chart needs at least one series.');
  const dashAttrs=i=>{const patterns=l.dash_patterns||['solid'];const tier=Math.floor(i/c.categorical.length);if(tier>=patterns.length)throw Error('Too many series for the available colors and dash patterns.');const pattern={solid:null,dashed:[3.7,1.6],dotted:[1,1.65],dashdot:[6.4,1.6,1,1.6]}[patterns[tier]];return pattern?{'stroke-dasharray':pattern.map(v=>v*l.data_linewidth_pt).join(' ')}:{};};
  const xs=spec.kind!=='bar'?spec.x:spec.categories.map((_,i)=>i);
  const ys=spec.kind!=='bar'?spec.series.flatMap(s=>s.y):spec.values;
  if(spec.kind==='bar' && spec.categories.length!==spec.values.length)throw Error('Bar values must have the same length as categories.');
  if(!xs.length||!ys.length||!xs.concat(ys).every(Number.isFinite))throw Error('Chart data must be finite numbers.');
  if(spec.kind!=='bar'&&spec.series.some(s=>s.y.length!==xs.length))throw Error('Each series y must have the same length as x.');
  let x0,x1,y0,y1;
  if(spec.kind!=='bar'){
    x0=Math.min(...xs);x1=Math.max(...xs);if(x0===x1){const d=Math.abs(x0)*.05||.05;x0-=d;x1+=d;}const dx=x1-x0;x0-=dx*a.margin_x;x1+=dx*a.margin_x;
    y0=Math.min(...ys);y1=Math.max(...ys);if(y0===y1){const d=Math.abs(y0)*.05||.05;y0-=d;y1+=d;}const dy=y1-y0;y0-=dy*a.margin_y;y1+=dy*a.margin_y;
  }else{
    x0=-.5-a.margin_x;x1=xs.length-.5+a.margin_x;
    y0=Math.min(0,...ys);y1=Math.max(0,...ys);const dy=(y1-y0)||1;
    if(y0<0)y0-=dy*a.margin_y;if(y1>0)y1+=dy*a.margin_y;if(y0===y1)y1=1;
  }
  const xt=spec.kind!=='bar'?ticks(x0,x1,a.max_xticks):spec.categories.map((text,i)=>({value:i,label:text}));
  const yt=ticks(y0,y1,a.max_yticks);
  const maxY=Math.max(...yt.map(t=>measure(t.label,ytick,weight('ytick'))));
  const maxX=Math.max(...xt.map(t=>measure(t.label,xtick,weight('xtick'))));
  const rotation=spec.kind==='bar'?p.bar.category_label_rotation_deg:0;
  const angle=rotation*Math.PI/180;
  const xExtent=Math.abs(Math.sin(angle))*maxX+Math.abs(Math.cos(angle))*Math.max(...xt.map(t=>metrics(t.label,xtick,weight('xtick')).height));
  const left=pad+metrics(spec.y_label,ylabel,weight('y_label')).height+4+maxY+l.tick_length_pt+l.tick_pad_pt;
  const top=pad+(spec.title?f.size_title_pt+4:0);
  // Leave room for the final numeric tick's ink, accounting for the data
  // margin between that tick and the plot edge (rather than padding twice).
  const fraction=(xt.at(-1).value-x0)/(x1-x0);
  let right=width-pad;
  if(spec.kind!=='bar') {
    const edge=width-pad-measure(xt.at(-1).label,xtick,weight('xtick'))/2;
    if(atlas) {
      // Matplotlib's constrained-layout runs two correction passes from the
      // default subplot box. Mirror those passes for this fixed template,
      // rather than solving the limiting equation to a different answer.
      const first=edge+(width*.9-width*.125)*(1-fraction);
      right=Math.min(width-pad,edge+(first-left)*(1-fraction));
    } else right=Math.min(width-pad,(edge-left*(1-fraction))/fraction);
  }
  const bottom=height-pad-metrics(spec.x_label,xlabel,weight('x_label')).height-4-xExtent-l.tick_length_pt-l.tick_pad_pt;
  if(right-left<30||bottom-top<20)throw Error('Not enough room at these dimensions and type sizes. Increase the canvas or reduce type size.');
  const X=v=>left+(v-x0)/(x1-x0)*(right-left),Y=v=>bottom-(v-y0)/(y1-y0)*(bottom-top);
  const svg=node('svg',{xmlns:NS,width:`${p.canvas.width_mm}mm`,height:`${height*25.4/72}mm`,viewBox:`0 0 ${width} ${height}`,
    role:'img','aria-label':`${spec.kind} figure: ${spec.y_label} versus ${spec.x_label}`,'font-family':'Chart Demo Sans',fill:c.text});
  svg.append(node('rect',{width,height,fill:p.canvas.background}));
  const text=(value,x,y,size,anchor='middle',attrs={})=>{
    activeWeight=f['weight_'+({xlabel:'x_label',ylabel:'y_label',xtick:'xtick',ytick:'ytick','legend-label':'legend'}[attrs.class]||'title')]??f.weight;
    const common={x,y,'font-size':size,'text-anchor':anchor,'data-chart-text':value,...attrs};
    if(!atlas)return node('text',common,value);
    const glyph=shape(value),width=glyph.width*size/100;
    const left=x-(anchor==='middle'?width/2:anchor==='end'?width:0);
    const group=node('g',{...common,role:'img','aria-label':value});
    group.append(node('title',{},value));
    const paths=node('g',{transform:`translate(${left} ${y}) scale(${size/100} ${-size/100})`});
    for(const part of glyph.parts||[{path:glyph.path,x:0}])paths.append(node('path',{d:part.path,transform:`translate(${part.x} 0)`}));
    group.append(paths);activeWeight='normal';
    return group;
  };
  const line=(x1,y1,x2,y2,stroke,w,attrs={})=>node('line',{x1,y1,x2,y2,stroke,'stroke-width':w,...attrs});
  const clipId=`chart-demo-${++sequence}`;
  const defs=node('defs'),clip=node('clipPath',{id:clipId});clip.append(node('rect',{x:left,y:top,width:right-left,height:bottom-top}));defs.append(clip);svg.append(defs);
  if(a.grid_enabled)for(const t of yt)svg.append(line(left,Y(t.value),right,Y(t.value),c.grid,a.grid_linewidth_pt,{'stroke-opacity':a.grid_alpha,'stroke-dasharray':'0.5 0.825',class:'grid-line'}));
  const data=node('g',{'clip-path':`url(#${clipId})`,class:'data'});
  if(spec.kind!=='bar'){
    const every=Math.max(1,Math.ceil(xs.length/l.max_markers_per_series));
    spec.series.forEach((series,i)=>{
      const color=c.categorical[i%c.categorical.length];
      const path=node('path',{d:xs.map((x,j)=>`${j?'L':'M'}${X(x)},${Y(series.y[j])}`).join(' '),fill:'none',stroke:color,'stroke-width':l.data_linewidth_pt,'stroke-linecap':'round','stroke-linejoin':'round',class:'data-line','data-series':i,...dashAttrs(i)});
      if(spec.kind==='line')data.append(path);
      if(l.markers_enabled || spec.kind==='scatter')xs.forEach((x,j)=>{if(spec.kind==='scatter' || j%every===0)data.append(drawMarker(l.markers[i%l.markers.length],X(x),Y(series.y[j]),l.marker_size_pt,color,{'data-series':i,'data-point':j,class:'data-marker'}));});
    });
  }else{
    spec.values.forEach((value,i)=>data.append(node('rect',{x:X(i-p.bar.width_fraction/2),y:Math.min(Y(0),Y(value)),width:X(p.bar.width_fraction)-X(0),height:Math.abs(Y(value)-Y(0)),fill:c.categorical[0],stroke:c.axes,'stroke-width':p.bar.edge_linewidth_pt,class:'data-bar','data-value':value,'data-index':i})));
    data.append(line(left,Y(0),right,Y(0),c.axes,p.bar.zero_line_linewidth_pt,{class:'zero-line'}));
  }
  svg.append(data);
  svg.append(line(left,top,left,bottom,c.axes,l.axes_linewidth_pt,{class:'y-spine','stroke-linecap':'square'}),line(left,bottom,right,bottom,c.axes,l.axes_linewidth_pt,{class:'x-spine','stroke-linecap':'square'}));
  for(const t of yt){
    svg.append(line(left-l.tick_length_pt,Y(t.value),left,Y(t.value),c.axes,l.tick_linewidth_pt));
    svg.append(text(t.label,left-l.tick_length_pt-l.tick_pad_pt,Y(t.value)+(atlas?metrics(t.label,ytick,weight('ytick')).ascent/2:ytick*.36),ytick,'end',{class:'ytick','data-value':t.value}));
  }
  for(const t of xt){
    svg.append(line(X(t.value),bottom,X(t.value),bottom+l.tick_length_pt,c.axes,l.tick_linewidth_pt));
    const x=X(t.value),y=bottom+l.tick_length_pt+l.tick_pad_pt+metrics(t.label,xtick,weight('xtick')).ascent;
    svg.append(text(t.label,x,y,xtick,rotation?'end':'middle',{class:'xtick','data-value':t.value,...(rotation?{transform:`rotate(${-rotation} ${x} ${y})`}:{})}));
  }
  svg.append(text(spec.x_label,(left+right)/2,height-pad-(atlas?metrics(spec.x_label,xlabel,weight('x_label')).descent:xlabel*.22),xlabel,'middle',{class:'xlabel'}));
  const ly=(top+bottom)/2,lx=pad+metrics(spec.y_label,ylabel,weight('y_label')).ascent;
  svg.append(text(spec.y_label,lx,ly,ylabel,'middle',{transform:`rotate(-90 ${lx} ${ly})`,class:'ylabel'}));
  if(spec.title)svg.append(text(spec.title,(left+right)/2,pad+f.size_title_pt,f.size_title_pt));
  if(spec.kind!=='bar'&&(spec.series.length>1||p.legend.show_for_single_series)){
    const handle=legend*p.legend.handlelength,row=(atlas?Math.max(...spec.series.map(s=>metrics(s.name,legend,weight('legend')).height)):legend)+legend*p.legend.label_spacing,gap=legend*.8;
    const lw=handle+gap+Math.max(...spec.series.map(s=>measure(s.name,legend,weight('legend')))),lh=spec.series.length*row;
    const inset=atlas?legend*p.legend.border_pad:0;
    let legendX=right-legend*.5-inset-lw,legendY=top+legend*.5+inset;
    if(p.legend.location==='best'){
      const choices=[[legendX,legendY],[left+legend*.5+inset,legendY],[legendX,bottom-legend*.5-inset-lh],[left+legend*.5+inset,bottom-legend*.5-inset-lh]];
      const hits=([x,y])=>spec.series.reduce((sum,s)=>sum+xs.filter((v,j)=>X(v)>=x-l.marker_size_pt/2 && X(v)<=x+lw+l.marker_size_pt/2 && Y(s.y[j])>=y-l.marker_size_pt/2 && Y(s.y[j])<=y+lh+l.marker_size_pt/2).length,0);
      const best=choices.map(pos=>({pos,score:hits(pos)})).sort((a,b)=>a.score-b.score)[0];
      [legendX,legendY]=best.pos;
    }
    const group=node('g',{class:'legend'});
    if(p.legend.frame)group.append(node('rect',{x:legendX-2,y:legendY-2,width:lw+4,height:lh+4,fill:'white',stroke:'#ccc','stroke-width':.5}));
    spec.series.forEach((series,i)=>{
      const color=c.categorical[i%c.categorical.length],baseline=legendY+i*row+metrics(series.name,legend,weight('legend')).ascent;
      const y=atlas?baseline-legend*.35:legendY+i*row+legend*.5;
      if(spec.kind==='line')group.append(line(legendX,y,legendX+handle,y,color,l.data_linewidth_pt,{'stroke-linecap':'round',...dashAttrs(i)}));
      if(l.markers_enabled || spec.kind==='scatter')group.append(drawMarker(l.markers[i%l.markers.length],legendX+handle/2,y,l.marker_size_pt,color));
      group.append(text(series.name,legendX+handle+gap,(atlas?baseline:y+legend*.36),legend,'start',{class:'legend-label'}));
    });svg.append(group);
  }
  return {svg,geometry:{width,height,left,right,top,bottom,xDomain:[x0,x1],yDomain:[y0,y1],xticks:xt,yticks:yt},
    note:'Independent SVG layout. Best legend placement scores data points in four corners; this is not Matplotlib constrained-layout or its full legend solver.'};
}

export function inspectNativeChart(svg) {
  const warnings=[],texts=[...svg.querySelectorAll('[data-chart-text]')],box=svg.viewBox.baseVal;
  for(const t of texts){const b=t.getBBox(),m=t.getCTM(),root=svg.getCTM().inverse();
    const points=[[b.x,b.y],[b.x+b.width,b.y],[b.x,b.y+b.height],[b.x+b.width,b.y+b.height]].map(([x,y])=>new DOMPoint(x,y).matrixTransform(root.multiply(m)));
    if(points.some(p=>p.x<-.5||p.y<-.5||p.x>box.width+.5||p.y>box.height+.5))warnings.push(`Text outside canvas: ${t.textContent}`);
  }
  const labels=[...svg.querySelectorAll('.xtick')];
  for(let i=1;i<labels.length;i++){
    const a=labels[i-1].getBoundingClientRect(),b=labels[i].getBoundingClientRect();
    if(a.right>b.left&&a.bottom>b.top&&b.bottom>a.top)warnings.push('X tick labels overlap; widen the figure, rotate labels or reduce tick type.');
  }
  return [...new Set(warnings)];
}
