import {EXPERIENCE_RULES} from './experience-rules.js';
import {PAPER_CHECK_RULES} from './paper-checks.js';

// Lesson IDs map to the skill catalog, not to a new set of quality thresholds.
// Controls are moved into these lessons; each path still has one input/handler.
export const RULE_LESSONS = [
  {id:'type-size',number:'01',title:'Type in context',
    rules:['paper-relative-typography','axis-label-consistency'],
    principle:'Aim for axis labels around 90% of body text, with matching X/Y sizes. Keep ticks and legends readable.',
    try:'Try making one axis label larger than the other, or shrinking the ticks. Watch the figure and the checks together.',
    paths:['fonts.size_x_label_pt','fonts.size_y_label_pt','fonts.size_xtick_pt','fonts.size_ytick_pt','fonts.size_title_pt'],
    experiment:'oversized-type',experimentLabel:'Try oversized labels',restore:'restore-type'},
  {id:'legend',number:'02',title:'Keep legends clear',kinds:['line','scatter'],
    rules:['legend-data-clearance','outside-legend-layout','paper-relative-typography'],
    principle:'A legend needs its own reading space. Even a transparent legend can hide the curve or marks behind its text.',
    try:'Compare an inside legend with a separate one. Choose a side and see how reserving space changes the plot.',
    paths:['legend.placement','legend.side','fonts.size_legend_pt'],
    experiment:'large-legend',experimentLabel:'Try a large inside legend',restore:'restore-legend'},
  {id:'lines',number:'03',title:'Make strokes distinguishable',
    rules:['print-strokes','series-distinguishability'],
    principle:'Thin strokes can disappear in print. Keep data, axes and ticks clear without letting them merge into a heavy band.',
    try:'Drag the line widths down, then compare with the reference. There is no universal upper line-width cutoff.',
    paths:['lines.data_linewidth_pt','lines.axes_linewidth_pt','lines.tick_linewidth_pt','bar.edge_linewidth_pt','bar.zero_line_linewidth_pt'],
    experiment:'hairlines',experimentLabel:'Try hairline strokes',restore:'restore-strokes'},
  {id:'axes',number:'04',title:'Give labels room',
    rules:['text-legibility','plot-area'],
    principle:'More ticks are useful only while their labels remain readable. Labels and decorations must also leave room for the data.',
    try:'Increase tick counts or change the category angle on a bar chart. Look for collisions instead of hiding categories.',
    paths:['axes.max_xticks','axes.max_yticks','lines.tick_length_pt','lines.tick_pad_pt','bar.category_label_rotation_deg'],
    experiment:'crowded-ticks',experimentLabel:'Try crowded ticks',restore:'restore-labels'},
  {id:'figure-size',number:'05',title:'Fit the paper',
    rules:['physical-size','wrapped-figure-width','article-fit'],
    principle:'The final paper slot sets the scale. A narrow wrapped figure cramps its caption; a wide one squeezes the prose.',
    try:'Drag the width and height. Type stays at the same physical size while the plot and surrounding text reflow.',paths:[]},
  {id:'space',number:'06',title:'Balance marks and space',
    rules:['marker-overdraw','recoverable-space','ink-context','bar-space-distribution'],
    principle:'Crowding and unused space are different problems. Ink coverage and the number of bars do not measure scientific information.',
    try:'Enlarge the marks, adjust margins, or try a bar example. Compare the space analysis at the lower left; preserve every value.',
    paths:['lines.marker_size_pt','lines.max_markers_per_series','axes.margin_x','axes.margin_y','bar.width_fraction'],
    experiment:'large-marks',experimentLabel:'Try larger marks',restore:'restore-space'},
];

export const EXTRA_GROUPS = [
  {id:'type-weight',parent:'type-size',label:'Advanced: type weight',paths:[
    'fonts.weight_x_label','fonts.weight_y_label','fonts.weight_xtick','fonts.weight_ytick','fonts.weight_legend','fonts.weight_title']},
  {id:'grid-style',parent:'lines',label:'Advanced: grid appearance',paths:['axes.grid_alpha','axes.grid_linewidth_pt']},
];

const fixed=n=>Number(n).toFixed(1);
const size=(profile,axis)=>profile.fonts[`size_${axis}_label_pt`]??profile.fonts.size_axis_label_pt;

export function lessonReference(id,page,profile){
  const t=EXPERIENCE_RULES.typography,b=page.preview_settings.body_size_pt;
  if(id==='type-size')return `Body ${fixed(b)} pt · Axis ${fixed(t.axis_labels.minimum_pt)}–${fixed(t.axis_labels.maximum_pt)} pt · Ticks ${fixed(t.tick_labels.minimum_pt)}–${fixed(t.tick_labels.maximum_pt)} pt · Legend ${fixed(b*t.legend.minimum_body_ratio)}–${fixed(b*t.legend.maximum_body_ratio)} pt`;
  if(id==='legend')return `Legend ${fixed(b*t.legend.minimum_body_ratio)}–${fixed(b*t.legend.maximum_body_ratio)} pt. Inside: protect its reading area. Separate: reserve space within the same canvas.`;
  if(id==='lines'){const s=EXPERIENCE_RULES.strokes;return `Reference: data ${fixed(s.data_default_pt)} pt · axes / ticks ${fixed(s.axes_default_pt)} pt · Review below ${s.minimum_checked_pt} pt`;}
  if(id==='axes')return 'Keep all category labels. Try rotation, fewer numeric ticks, or more physical room before shrinking text.';
  if(id==='figure-size')return page.layout.text_wrap?`Text wrap: aim for ⅓–⅔ of body width; leave at least ${PAPER_CHECK_RULES.minimumWrapTextMm} mm for prose.`:'Non-wrapped placement: the wrapped-width recommendation does not apply. Keep the figure inside its text block.';
  return 'Overdraw and recoverable space are heuristics. Figure / body ink and bar distribution are descriptive only.';
}

export function lessonReading(id,page,profile){
  if(id==='type-size')return `Now: X ${fixed(size(profile,'x'))} pt / Y ${fixed(size(profile,'y'))} pt · ${Math.round(size(profile,'x')/page.preview_settings.body_size_pt*100)}% / ${Math.round(size(profile,'y')/page.preview_settings.body_size_pt*100)}% of body`;
  if(id==='figure-size')return `Now: ${fixed(page.figure.width_mm)} × ${fixed(page.figure.height_mm)} mm · ${Math.round(page.figure.width_mm/page.text_block.width_mm*100)}% of body width`;
  return '';
}

export function lessonChecks(id,report){
  const checks=report?.checks||[];
  const suffix=(c,names)=>names.some(name=>c.id.endsWith('.'+name));
  return checks.filter(c=>{
    if(id==='type-size')return c.category==='typography'||suffix(c,['minimum_text_size']);
    if(id==='legend')return suffix(c,['legend_data_overlap','size_legend_pt']);
    if(id==='lines')return suffix(c,['thin_strokes']);
    if(id==='axes')return suffix(c,['tick_label_overlap','text_within_canvas','plot_area']);
    if(id==='figure-size')return c.id.startsWith('paper.')&&c.category!=='typography';
    return suffix(c,['mark_overdraw','space_utilization','invisible_data']);
  });
}

export function experimentEdits(action,base,page){
  const t=EXPERIENCE_RULES.typography;
  const defaults=paths=>Object.fromEntries(paths.map(path=>[path,path.split('.').reduce((o,k)=>o[k],base)]));
  switch(action){
    case 'oversized-type':return {'fonts.size_x_label_pt':page.preview_settings.body_size_pt*1.2,'fonts.size_y_label_pt':page.preview_settings.body_size_pt*1.2};
    case 'restore-type':return {'fonts.size_x_label_pt':t.axis_labels.recommended_pt,'fonts.size_y_label_pt':t.axis_labels.recommended_pt,'fonts.size_xtick_pt':t.tick_labels.recommended_pt,'fonts.size_ytick_pt':t.tick_labels.recommended_pt,'fonts.size_legend_pt':page.preview_settings.body_size_pt*t.legend.minimum_body_ratio};
    case 'large-legend':return {'legend.placement':'inside','fonts.size_legend_pt':14};
    case 'restore-legend':return defaults(['legend.placement','fonts.size_legend_pt']);
    case 'hairlines':return {'lines.data_linewidth_pt':.15,'lines.axes_linewidth_pt':.15,'lines.tick_linewidth_pt':.15};
    case 'restore-strokes':return defaults(['lines.data_linewidth_pt','lines.axes_linewidth_pt','lines.tick_linewidth_pt']);
    case 'crowded-ticks':return {'axes.max_xticks':24,'axes.max_yticks':24,'bar.category_label_rotation_deg':0};
    case 'restore-labels':return defaults(['axes.max_xticks','axes.max_yticks','bar.category_label_rotation_deg']);
    case 'large-marks':return {'lines.marker_size_pt':10};
    case 'restore-space':return defaults(['lines.marker_size_pt']);
    default:throw new Error(`Unknown rule experiment: ${action}`);
  }
}
