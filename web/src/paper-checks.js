import {evaluateTypography} from './typography-checks.js';
import {EXPERIENCE_RULES} from './experience-rules.js';
/** Paper-context rules. These are editable project preferences, not venue rules. */
export const PAPER_CHECK_RULES = {minimumWrapTextMm: 30};
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
    const rules=EXPERIENCE_RULES.wrapped_figure,ratio=page.figure.width_mm/body.width_mm;
    const remaining=body.width_mm-page.figure.width_mm-page.preview_settings.wrap_gap_mm;
    const evidence={figure_width_mm:page.figure.width_mm,body_width_mm:body.width_mm,body_width_ratio:ratio,
      minimum_recommended_mm:body.width_mm*rules.minimum_recommended_ratio,maximum_recommended_mm:body.width_mm*rules.maximum_recommended_ratio,
      caption_cramped:ratio<rules.caption_cramped_below_ratio-1e-9,remaining_text_mm:Math.max(0,remaining)};
    if(ratio<rules.minimum_recommended_ratio-1e-9){
      add('wrap_figure_narrow','Wrapped figure is too narrow',`The figure uses ${(ratio*100).toFixed(1)}% of the body width. For text wrapping, use about one third to two thirds of the body width.${evidence.caption_cramped?' Below one quarter, the caption may wrap excessively.':''}`,'figure-width');
      Object.assign(checks.at(-1),{rule_id:rules.id,measurements:evidence});
    }
    if(ratio>rules.maximum_recommended_ratio+1e-9 || remaining<PAPER_CHECK_RULES.minimumWrapTextMm){
      add('wrap_width','Body text is squeezed',`The figure uses ${(ratio*100).toFixed(1)}% of the body width, leaving ${Math.max(0,remaining).toFixed(1)} mm beside it. For text wrapping, keep the figure at most two thirds of the body width and leave at least ${PAPER_CHECK_RULES.minimumWrapTextMm} mm for prose.`,'figure-width');
      Object.assign(checks.at(-1),{rule_id:rules.id,measurements:evidence});
    }
  }
  // Text ranges give actual line fragments; paragraph rectangles incorrectly
  // include the float region even when every word wraps safely around it.
  let collides=false;
  for(const fragment of paper.querySelectorAll('.flow-fragment')){
    const range=document.createRange();range.selectNodeContents(fragment);
    if([...range.getClientRects()].some(r=>Math.min(r.right,box.right)-Math.max(r.left,box.left)>pxPerMm*.3 && Math.min(r.bottom,box.bottom)-Math.max(r.top,box.top)>pxPerMm*.3)){collides=true;break;}
  }
  if(collides)add('body_overlap','Figure overlaps body text','The figure or caption intersects surrounding text. Reduce the figure width or height.','figure-width');
  checks.push(...evaluateTypography(page,profile,spec));
  return checks;
}
export function combinedReport(figureReport, paperChecks) {
  const relativeMinimums=new Set(paperChecks.filter(c=>c.category==='typography'&&c.measurements.lower_bound_violated).map(c=>c.control));
  // Relative-to-body warnings are more actionable than a duplicate 6 pt warning.
  // Keep the absolute check when any affected role (e.g. title) is not covered.
  const figureChecks=figureReport.checks.filter(c=>!c.id.endsWith('.minimum_text_size') ||
    !c.affected_controls?.every(control=>relativeMinimums.has(control)));
  const checks=[...figureChecks,...paperChecks];
  const counts={pass:0,warn:0,fail:0,not_checked:0};
  for(const c of checks)counts[c.status]=(counts[c.status]||0)+1;
  return {...figureReport,experience_rules:EXPERIENCE_RULES,checks,counts,status:counts.fail?'fail':counts.warn?'warn':'pass',paper_context_checked:true};
}
