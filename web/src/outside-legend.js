/** One figure-level legend, allocated beside (never over) the panel grid. */
import {createChartText,node,marker,seriesDashAttrs} from './native-chart.js';

export function outsideLegendEntries(spec,p){
  const panels=spec.kind==='grid'?spec.panels:[spec],entries=new Map();
  panels.forEach((panel,panelIndex)=>{
    if(panel.kind==='bar')return;
    panel.series.forEach((series,i)=>{
      const color=p.colors.categorical[i%p.colors.categorical.length];
      const symbol=p.lines.markers[i%p.lines.markers.length];
      const hasMarker=panel.kind==='scatter'||p.lines.markers_enabled;
      const key=JSON.stringify([series.name,panel.kind,color,panel.kind==='line'?seriesDashAttrs(i,p):null,hasMarker?symbol:null]);
      if(entries.has(key))entries.get(key).panel_indices.push(panelIndex);
      else entries.set(key,{name:series.name,source_name:series.name,kind:panel.kind,series_index:i,panel_indices:[panelIndex]});
    });
  });
  const result=[...entries.values()],cols=spec.kind==='grid'?spec.columns:1;
  for(const e of result)if(result.some(other=>other!==e&&other.source_name===e.source_name)){
    const positions=e.panel_indices.map(i=>`${Math.floor(i/cols)+1}:${i%cols+1}`).join(', ');
    e.name=`Panel ${positions} - ${e.source_name}`;
  }
  return result;
}

export function renderOutsideLegend(spec,p,atlas){
  const entries=outsideLegendEntries(spec,p);
  if(!entries.length)return null;
  const {measure,metrics,text}=createChartText(p,atlas),size=p.fonts.size_legend_pt;
  const weight=p.fonts.weight_legend??p.fonts.weight;
  const padding=Math.max(size*p.legend.border_pad,p.lines.marker_size_pt/2,p.lines.data_linewidth_pt/2)+2;
  const handle=size*p.legend.handlelength,gap=size*.8;
  const row=Math.max(...entries.map(e=>metrics(e.name,size,weight).height),p.lines.marker_size_pt)+size*p.legend.label_spacing;
  const columns=Math.max(1,Math.min(entries.length,Math.floor(p.legend.columns))),positions=[];
  let x=padding,start=0,maxRows=0;
  for(let column=0;column<columns;column++){
    const count=Math.floor(entries.length/columns)+(column<entries.length%columns?1:0);
    const items=entries.slice(start,start+count);
    items.forEach((e,r)=>positions.push({x,row:r}));
    x+=handle+gap+Math.max(...items.map(e=>measure(e.name,size,weight)))+(column<columns-1?2*size:0);
    start+=count;maxRows=Math.max(maxRows,count);
  }
  const width=x+padding,height=2*padding+row*maxRows-size*p.legend.label_spacing;
  const svg=node('svg',{xmlns:'http://www.w3.org/2000/svg',width:`${width}pt`,height:`${height}pt`,viewBox:`0 0 ${width} ${height}`,fill:p.colors.text});
  const group=node('g',{class:'legend legend-outside','data-placement':'outside'});
  group.append(node('rect',{class:'legend-frame',x:0,y:0,width,height,rx:2,fill:p.canvas.background,stroke:p.colors.axes,'stroke-width':p.lines.axes_linewidth_pt}));
  entries.forEach((entry,j)=>{
    const i=entry.series_index,color=p.colors.categorical[i%p.colors.categorical.length];
    const left=positions[j].x,baseline=padding+positions[j].row*row+metrics(entry.name,size,weight).ascent,y=baseline-size*.35;
    const item=node('g',{'data-legend-entry':entry.name,'data-panels':entry.panel_indices.join(',')});
    if(entry.kind==='line')item.append(node('line',{x1:left,y1:y,x2:left+handle,y2:y,stroke:color,'stroke-width':p.lines.data_linewidth_pt,'stroke-linecap':'round',...seriesDashAttrs(i,p)}));
    if(p.lines.markers_enabled||entry.kind==='scatter'){
      const symbol=p.lines.markers[i%p.lines.markers.length],x=left+handle/2;
      item.append(atlas?node('path',{d:atlas.markers[symbol],transform:`translate(${x} ${y}) scale(${p.lines.marker_size_pt} ${-p.lines.marker_size_pt})`,fill:color}):marker(symbol,x,y,p.lines.marker_size_pt,color));
    }
    item.append(text(entry.name,left+handle+gap,baseline,size,'start',{class:'legend-label'}));
    group.append(item);
  });
  svg.append(group);
  return {svg,width,height,entries};
}
