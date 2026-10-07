/** Paper-context rules. These are editable project preferences, not venue rules. */
export const PAPER_CHECK_RULES = {minimumWrapTextMm: 30, minimumTypeRatio: .65, maximumTypeRatio: 1.6};
export function evaluatePaper(page, profile, spec, paper) {
  const checks=[];
  const add=(id,title,message,control)=>checks.push({id:`paper.${id}`,status:'warn',title,message,control});
  const figure=paper.querySelector('.reflow-figure');
  if(!figure)return checks;
  const sheet=paper.getBoundingClientRect(),box=figure.getBoundingClientRect();
  const pxPerMm=sheet.width/page.paper.width_mm;
  const body=page.text_block;
  if(box.bottom>sheet.top+(body.top_mm+body.height_mm)*pxPerMm+.5)
    add('figure_height','Figure reaches the page margin','The figure and caption extend below the text area. Reduce figure height to keep them clear of the footer.','figure-height');
  if(box.left<sheet.left+body.left_mm*pxPerMm-.5 || box.right>sheet.left+(body.left_mm+body.width_mm)*pxPerMm+.5)
    add('figure_width','Figure exceeds text width','The figure extends beyond the template text block. Reduce its width.','figure-width');
  if(page.layout.text_wrap){
    const remaining=body.width_mm-page.figure.width_mm-page.preview_settings.wrap_gap_mm;
    if(remaining<PAPER_CHECK_RULES.minimumWrapTextMm)
      add('wrap_width','Body text is squeezed',`Only ${Math.max(0,remaining).toFixed(1)} mm remains beside the figure. Aim for at least ${PAPER_CHECK_RULES.minimumWrapTextMm} mm of readable body text.`,'figure-width');
  }
  // Text ranges give actual line fragments; paragraph rectangles incorrectly
  // include the float region even when every word wraps safely around it.
  let collides=false;
  for(const fragment of paper.querySelectorAll('.flow-fragment')){
    const range=document.createRange();range.selectNodeContents(fragment);
    if([...range.getClientRects()].some(r=>Math.min(r.right,box.right)-Math.max(r.left,box.left)>pxPerMm*.3 && Math.min(r.bottom,box.bottom)-Math.max(r.top,box.top)>pxPerMm*.3)){collides=true;break;}
  }
  if(collides)add('body_overlap','Figure overlaps body text','The figure or caption intersects surrounding text. Reduce the figure width or height.','figure-width');
  const panels=spec.kind==='grid'?spec.panels:[spec],f=profile.fonts;
  const roles=[['size_x_label_pt','size_axis_label_pt'],['size_y_label_pt','size_axis_label_pt'],['size_xtick_pt','size_tick_pt'],['size_ytick_pt','size_tick_pt']];
  if(panels.some(p=>p.series?.length>1 || p.series && profile.legend.show_for_single_series))roles.push(['size_legend_pt','size_legend_pt']);
  const values=roles.map(([key,fallback])=>f[key]??f[fallback]);
  const bodyType=page.preview_settings.body_size_pt;
  if(Math.min(...values)>=6 && Math.min(...values)<bodyType*PAPER_CHECK_RULES.minimumTypeRatio)
    add('type_too_small','Figure text is small beside prose',`The smallest figure text is ${Math.min(...values)} pt beside ${bodyType} pt body text. Consider increasing the smaller labels.`,'fonts.'+roles[values.indexOf(Math.min(...values))][0]);
  if(Math.max(...values)>bodyType*PAPER_CHECK_RULES.maximumTypeRatio)
    add('type_too_large','Figure text dominates the page',`Figure labels reach ${Math.max(...values)} pt beside ${bodyType} pt body text. Check the balance at the intended print size.`,'fonts.'+roles[values.indexOf(Math.max(...values))][0]);
  return checks;
}
export function combinedReport(figureReport, paperChecks) {
  const checks=[...figureReport.checks,...paperChecks];
  const counts={pass:0,warn:0,fail:0,not_checked:0};
  for(const c of checks)counts[c.status]=(counts[c.status]||0)+1;
  return {...figureReport,checks,counts,status:counts.fail?'fail':counts.warn?'warn':'pass',paper_context_checked:true};
}
