import { measureFigureDensity } from './figure-density.js';
/** Extend this list with additional scale/legibility checks.
 * Thresholds are project defaults, not conference requirements. Units are pt.
 */
export const FIGURE_CHECK_RULES = { minimumTextPt: 6, minimumStrokePt: .25, minimumPlotFraction: .2 };
export function evaluateFigure(svg,panelIndex,profile,geometry) {
  const checks=[],texts=[...svg.querySelectorAll('[data-chart-text]')];
  const add=(id,title,message,control,subjects=[])=>checks.push({panel_index:panelIndex,subjects,id:`panel_${panelIndex+1}.${id}`,title,status:'warn',control,message:`Panel ${panelIndex+1}: ${message}`});
  const boxes=texts.map(n=>({node:n,rect:n.getBoundingClientRect()}));
  const overlap=[],overlapSubjects=new Set();
  for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++){
    const a=boxes[i].rect,b=boxes[j].rect;
    if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>.5 && Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>.5)
      {overlap.push(`“${boxes[i].node.dataset.chartText}” / “${boxes[j].node.dataset.chartText}”`);overlapSubjects.add(boxes[i].node.dataset.chartText);overlapSubjects.add(boxes[j].node.dataset.chartText);}
  }
  if(overlap.length)add('tick_label_overlap','Text overlap',`${overlap.slice(0,3).join('; ')}${overlap.length>3?'…':''}. Widen the figure or reduce the label size.`,'figure-width',[...overlapSubjects]);
  const bounds=svg.getBoundingClientRect();
  const outside=boxes.filter(({rect:b})=>b.left<bounds.left-.7 || b.top<bounds.top-.7 || b.right>bounds.right+.7 || b.bottom>bounds.bottom+.7);
  if(outside.length)add('text_within_canvas','Text outside figure',`${outside.length} label(s) extend beyond the canvas. Increase the figure size.`,'figure-width',outside.map(b=>b.node.dataset.chartText));
  const controlForText=n=>'fonts.size_'+({xlabel:'x_label_pt',ylabel:'y_label_pt',xtick:'xtick_pt',ytick:'ytick_pt','legend-label':'legend_pt'}[n.getAttribute('class')]||'title_pt');
  const small=texts.filter(n=>Number(n.getAttribute('font-size'))<FIGURE_CHECK_RULES.minimumTextPt);
  if(small.length)add('minimum_text_size','Text too small',`${small.length} label(s) are below ${FIGURE_CHECK_RULES.minimumTextPt} pt at print size.`,controlForText(small[0]),small.map(n=>n.dataset.chartText));
  const thin=[...svg.querySelectorAll('.data-line,.x-spine,.y-spine')].filter(n=>{const w=Number(n.getAttribute('stroke-width'));return w>0 && w<FIGURE_CHECK_RULES.minimumStrokePt;});
  if(thin.length)add('thin_strokes','Lines may disappear in print',`Some data lines or axes are thinner than ${FIGURE_CHECK_RULES.minimumStrokePt} pt. Review them at print size.`,thin[0].classList.contains('data-line')?'lines.data_linewidth_pt':'lines.axes_linewidth_pt');
  if(geometry && (geometry.right-geometry.left)*(geometry.bottom-geometry.top)/(geometry.width*geometry.height)<FIGURE_CHECK_RULES.minimumPlotFraction)
    add('plot_area','Labels crowd the plot','Less than 20% of this panel is available for data. Increase the figure size or reduce oversized labels.','figure-height');
  const markers=[...svg.querySelectorAll('.data-marker')];
  if(markers.length && profile?.lines.marker_size_pt===0 && !svg.querySelector('.data-line'))
    add('invisible_data','Markers are invisible','Marker size is zero, so the scatter data cannot be seen.','lines.marker_size_pt');
  const density=geometry && measureFigureDensity(svg,geometry);
  if(density?.oversized){
    const percent=Math.round(density.largest_empty_rectangle_fraction*100);
    add('space_utilization','Figure may be oversized',`A contiguous empty region occupies about ${percent}% of the plotting area. Consider reducing figure height or width while keeping labels readable. This is a spacing heuristic, not a measure of scientific value.`,density.region.height>=density.region.width?'figure-height':'figure-width');
    Object.assign(checks.at(-1),{measurements:density,region:density.region});
  }
  return checks;
}
