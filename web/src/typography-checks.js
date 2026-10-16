import {EXPERIENCE_RULES} from './experience-rules.js';

/** Evaluate only text roles actually present. Shared styles yield one warning per role,
 * with all affected panels recorded; do not multiply a global style issue by grid size.
 */
export function evaluateTypography(page,profile,spec,rules=EXPERIENCE_RULES.typography){
  const panels=spec.kind==='grid'?spec.panels:[spec],f=profile.fonts,body=page.preview_settings.body_size_pt;
  const checks=[],size=(key,fallback)=>f[key]??f[fallback];
  const role=(key,label,actual,min,max,indices,extra={})=>{
    if(!indices.length || actual>=min-1e-9 && actual<=max+1e-9)return;
    const short=actual<min,control=`fonts.${key}`;
    const message=`${label} is ${actual} pt beside ${body} pt body text. Use ${min.toFixed(1)}–${max.toFixed(1)} pt for this role.`;
    checks.push({id:`paper.${key}`,status:'warn',title:`${label} size is ${short?'too small':'too large'}`,message,control,
      category:'typography',rule_id:rules.id,panel_indices:indices,
      measurements:{actual_pt:actual,body_pt:body,body_ratio:actual/body,minimum_pt:min,maximum_pt:max,
        lower_bound_violated:short,...extra}});
  };
  const indicesFor=predicate=>panels.flatMap((panel,i)=>predicate(panel)?[i]:[]);
  for(const axis of ['x','y']){
    const label=size(`size_${axis}_label_pt`,'size_axis_label_pt'),ticks=size(`size_${axis}tick_pt`,'size_tick_pt');
    const labelIndices=indicesFor(p=>Boolean(p[`${axis}_label`]));
    role(`size_${axis}_label_pt`,`${axis.toUpperCase()} axis label`,label,
      rules.axis_labels.minimum_pt,rules.axis_labels.maximum_pt,labelIndices);
    // Intersect the calibrated print-size range with 0.8 × the visible axis
    // label ± 1 pt. Invalid axis settings must not produce an impossible range.
    const all=indicesFor(()=>true),withLabel=labelIndices.length>0;
    const t=rules.tick_labels,target=label*t.target_axis_label_ratio;
    const relativeMin=target-t.axis_label_tolerance_pt,relativeMax=target+t.axis_label_tolerance_pt;
    let min=withLabel?Math.max(t.minimum_pt,relativeMin):t.minimum_pt;
    let max=withLabel?Math.min(t.maximum_pt,relativeMax):t.maximum_pt;
    const conflict=min>max;
    if(conflict){
      min=t.minimum_pt;max=t.maximum_pt;
      const labelWarning=checks.find(c=>c.id===`paper.size_${axis}_label_pt`);
      if(labelWarning)Object.assign(labelWarning.measurements,{tick_relative_constraint_deferred:true,
        axis_relative_tick_minimum_pt:relativeMin,axis_relative_tick_maximum_pt:relativeMax});
    }
    const affected=ticks<t.minimum_pt-1e-9 || ticks>t.maximum_pt+1e-9?all:withLabel?labelIndices:all;
    role(`size_${axis}tick_pt`,`${axis.toUpperCase()} tick labels`,ticks,min,max,affected,
      {axis_label_pt:withLabel?label:null,recommended_pt:t.recommended_pt,
        axis_relative_minimum_pt:withLabel?relativeMin:null,axis_relative_maximum_pt:withLabel?relativeMax:null,
        axis_relative_constraint_deferred:withLabel&&conflict});
  }
  const xLabel=size('size_x_label_pt','size_axis_label_pt'),yLabel=size('size_y_label_pt','size_axis_label_pt');
  const paired=indicesFor(p=>Boolean(p.x_label&&p.y_label));
  if(paired.length&&Math.abs(xLabel-yLabel)>rules.axis_labels.equal_size_tolerance_pt){
    checks.push({id:'paper.axis_label_consistency',status:'warn',title:'Axis label sizes differ',
      message:`X axis label is ${xLabel} pt and Y axis label is ${yLabel} pt. Use the same size for both axis labels.`,
      category:'typography',rule_id:rules.id,panel_indices:paired,control:'fonts.size_y_label_pt',
      measurements:{x_label_pt:xLabel,y_label_pt:yLabel,body_pt:body,maximum_difference_pt:rules.axis_labels.equal_size_tolerance_pt}});
  }
  role('size_legend_pt','Legend',f.size_legend_pt,
    body*rules.legend.minimum_body_ratio,body*rules.legend.maximum_body_ratio,
    indicesFor(p=>p.kind!=='bar'&&(profile.legend.placement==='outside'||p.series.length>1||profile.legend.show_for_single_series)));
  return checks;
}
