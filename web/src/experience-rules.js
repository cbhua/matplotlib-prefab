/** Versioned project experience rules. Values here are owner preferences, not venue requirements.
 * Add a rule's thresholds and provenance here; keep its evaluator in a focused module.
 */
export const EXPERIENCE_RULES = {
  version:'3',
  reference:'references/experience-rules.md',
  typography:{
    id:'paper-relative-typography',origin:'project-owner-preference',
    units:'physical points; a proxy for perceived size',
    axis_labels:{recommended_pt:9,minimum_pt:8.5,maximum_pt:9.5,equal_size_tolerance_pt:.01},
    tick_labels:{recommended_pt:8,minimum_pt:7.5,maximum_pt:8,target_axis_label_ratio:.8,axis_label_tolerance_pt:1},
    legend:{minimum_body_ratio:.8,maximum_body_ratio:1},
  },
  wrapped_figure:{
    id:'wrapped-figure-width',origin:'project-owner-preference',
    reference:'available body text width, excluding page margins',
    minimum_recommended_ratio:1/3,caption_cramped_below_ratio:1/4,maximum_recommended_ratio:2/3,
  },
  strokes:{
    id:'print-strokes',origin:'project defaults with publisher references',
    data_default_pt:1.2,axes_default_pt:.6,tick_default_pt:.6,
    minimum_checked_pt:.25,maximum_checked_pt:null,
    note:'Publisher lower limits vary; no general upper limit is enforced.',
  },
  bar_space:{
    id:'bar-space-distribution',origin:'descriptive geometry; no calibrated quality threshold',
    automatic_information_density_warning:false,
    note:'Category count and bar fill do not determine scientific information. Inspect pitch, gaps and spatial load before proposing a smaller canvas.',
  },
};
