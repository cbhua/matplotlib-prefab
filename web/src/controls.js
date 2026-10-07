/**
 * Every control the panel offers, and the profile field each one writes.
 *
 * This list is the contract. A control here that no renderer reads would be a
 * knob that does nothing — the most misleading thing this tool could ship — so
 * `tests/web/test_controls.py` renders the figure twice for every entry below
 * and fails if moving the control changes nothing.
 *
 * `min`, `max` and `step` are UI convenience, not science and not validation.
 * The number box accepts anything; only the active renderer validates what is a
 * legal profile, and it is deliberately more permissive than these sliders.
 */

/** Read `a.b` out of a profile. */
export function getPath(object, path) {
  return path.split('.').reduce((node, key) => (node == null ? undefined : node[key]), object);
}

/** Write `a.b`, creating nothing that was not already a section. */
export function setPath(object, path, value) {
  const parts = path.split('.');
  const last = parts.pop();
  const parent = parts.reduce((node, key) => (node[key] ??= {}), object);
  parent[last] = value;
}

export function deletePath(object, path) {
  const parts = path.split('.');
  const last = parts.pop();
  const parent = parts.reduce((node, key) => (node == null ? undefined : node[key]), object);
  if (parent) delete parent[last];
}

const WEIGHTS = ['normal', 'medium', 'semibold', 'bold'];

export const CONTROL_GROUPS = [
  {
    id: 'type-size',
    label: 'Type size',
    note: 'Points, at the printed size. The figure is drawn at the slot’s physical width, '
        + 'so a 9 pt label is 9 pt on the page.',
    controls: [
      { path: 'fonts.size_x_label_pt', fallback: 'fonts.size_axis_label_pt',
        label: 'X axis label', unit: 'pt', min: 4, max: 18, step: 0.25 },
      { path: 'fonts.size_y_label_pt', fallback: 'fonts.size_axis_label_pt',
        label: 'Y axis label', unit: 'pt', min: 4, max: 18, step: 0.25 },
      { path: 'fonts.size_xtick_pt', fallback: 'fonts.size_tick_pt',
        label: 'X tick labels', unit: 'pt', min: 3, max: 16, step: 0.25 },
      { path: 'fonts.size_ytick_pt', fallback: 'fonts.size_tick_pt',
        label: 'Y tick labels', unit: 'pt', min: 3, max: 16, step: 0.25 },
      { path: 'fonts.size_legend_pt', label: 'Legend', unit: 'pt', min: 3, max: 16, step: 0.25 },
      // A title control only does something when the spec has a title, so it is
      // marked as such and the panel disables it when there is none. A live knob
      // that silently changes nothing is the thing this tool must not ship.
      { path: 'fonts.size_title_pt', label: 'Title', unit: 'pt', min: 4, max: 20, step: 0.25,
        requiresTitle: true },
    ],
  },
  {
    id: 'type-weight',
    label: 'Type weight',
    note: 'Uses the matching Matplotlib font outlines for each weight. The exported profile retains '
        + 'the selected weight.',
    controls: [
      { path: 'fonts.weight_x_label', fallback: 'fonts.weight', label: 'X axis label',
        kind: 'choice', choices: WEIGHTS },
      { path: 'fonts.weight_y_label', fallback: 'fonts.weight', label: 'Y axis label',
        kind: 'choice', choices: WEIGHTS },
      { path: 'fonts.weight_xtick', fallback: 'fonts.weight', label: 'X tick labels',
        kind: 'choice', choices: WEIGHTS },
      { path: 'fonts.weight_ytick', fallback: 'fonts.weight', label: 'Y tick labels',
        kind: 'choice', choices: WEIGHTS },
      { path: 'fonts.weight_legend', fallback: 'fonts.weight', label: 'Legend',
        kind: 'choice', choices: WEIGHTS },
      { path: 'fonts.weight_title', fallback: 'fonts.weight', label: 'Title',
        kind: 'choice', choices: WEIGHTS, requiresTitle: true },
    ],
  },
  {
    id: 'lines',
    label: 'Lines and markers',
    controls: [
      { path: 'lines.data_linewidth_pt', kinds: ['line'], label: 'Data lines', unit: 'pt', min: 0.2, max: 4, step: 0.05 },
      { path: 'lines.axes_linewidth_pt', label: 'Axis spines', unit: 'pt', min: 0.1, max: 3, step: 0.05 },
      { path: 'lines.tick_linewidth_pt', label: 'Tick marks', unit: 'pt', min: 0.1, max: 3, step: 0.05 },
      { path: 'lines.tick_length_pt', label: 'Tick length', unit: 'pt', min: 0, max: 8, step: 0.25 },
      { path: 'lines.tick_pad_pt', label: 'Tick label gap', unit: 'pt', min: 0, max: 10, step: 0.25 },
      { path: 'lines.marker_size_pt', label: 'Marker size', unit: 'pt', min: 0, max: 12, step: 0.25 },
      { path: 'lines.max_markers_per_series', kinds: ['line'], label: 'Markers per series', unit: 'max',
        min: 2, max: 40, step: 1, integer: true },
    ],
  },
  {
    id: 'axes',
    label: 'Axes and grid',
    controls: [
      { path: 'axes.max_xticks', label: 'X tick count', unit: 'max', min: 2, max: 14, step: 1, integer: true },
      { path: 'axes.max_yticks', label: 'Y tick count', unit: 'max', min: 2, max: 14, step: 1, integer: true },
      { path: 'axes.grid_alpha', label: 'Grid opacity', unit: '', min: 0, max: 1, step: 0.05 },
      { path: 'axes.grid_linewidth_pt', label: 'Grid line width', unit: 'pt', min: 0.05, max: 2, step: 0.05 },
      { path: 'axes.margin_x', label: 'X data margin', unit: '', min: 0, max: 0.3, step: 0.01 },
      { path: 'axes.margin_y', label: 'Y data margin', unit: '', min: 0, max: 0.3, step: 0.01 },
    ],
  },
  {
    id: 'bar',
    label: 'Bars',
    note: 'Only affects the bar examples.',
    kinds: ['bar'],
    controls: [
      { path: 'bar.width_fraction', label: 'Bar width', unit: 'of slot', min: 0.1, max: 1, step: 0.05 },
      { path: 'bar.edge_linewidth_pt', label: 'Bar edge', unit: 'pt', min: 0, max: 2, step: 0.05 },
      { path: 'bar.zero_line_linewidth_pt', label: 'Zero line', unit: 'pt', min: 0, max: 2, step: 0.05 },
      { path: 'bar.category_label_rotation_deg', label: 'Category label angle', unit: '°',
        min: 0, max: 90, step: 5 },
    ],
  },
];

export const ALL_CONTROLS = CONTROL_GROUPS.flatMap((group) =>
  group.controls.map((control) => ({ ...control, group: group.id, groupKinds: group.kinds })));

/** Does this control affect a figure drawn from `spec`? */
export function controlApplies(control, spec) {
  if (spec?.kind === 'grid') return spec.panels.some(panel => controlApplies(control, panel));
  const kind = (spec && spec.kind) || 'line';
  if ((control.kinds || control.groupKinds) && !(control.kinds || control.groupKinds).includes(kind)) return false;
  if (control.requiresTitle && !(spec && typeof spec.title === 'string' && spec.title.trim())) {
    return false;
  }
  return true;
}

/** The value a control shows when the user has not touched it. */
export function effectiveValue(profile, control) {
  const own = getPath(profile, control.path);
  if (own !== undefined && own !== null) return own;
  if (control.fallback) return getPath(profile, control.fallback);
  return undefined;
}

export function isOverridden(profile, baseProfile, control) {
  const current = effectiveValue(profile, control);
  const base = effectiveValue(baseProfile, control);
  return String(current) !== String(base);
}

/**
 * Build the panel. `onChange(control, value)` fires on every edit;
 * `onReset(control | null)` resets one control or all of them.
 */
export function buildPanel(root, { onChange, onReset }) {
  const registry = new Map();
  root.textContent = '';

  const order=['type-size','lines','bar','axes','type-weight'];
  for (const group of [...CONTROL_GROUPS].sort((a,b)=>order.indexOf(a.id)-order.indexOf(b.id))) {
    const section = document.createElement('details');
    section.open=['type-size','lines','bar'].includes(group.id);
    section.className = 'panel-group';
    section.dataset.group = group.id;
    if (group.kinds) section.dataset.kinds = group.kinds.join(' ');

    const heading = document.createElement('summary');
    heading.textContent = group.label;
    section.appendChild(heading);

    for (const raw of group.controls) {
      // The group's `kinds` restriction belongs to each of its controls from
      // here on; sync() asks the control, not the group.
      const control = { ...raw, group: group.id, groupKinds: group.kinds };
      const row = document.createElement('div');
      row.className = 'control';
      row.dataset.path = control.path;

      const id = `control-${control.path.replace(/\./g, '-')}`;
      const label = document.createElement('label');
      label.htmlFor = id;
      label.className = 'control-label';
      label.textContent = control.label;
      const flag = document.createElement('span');
      flag.className = 'control-flag';
      flag.title = 'Changed from the profile default';
      flag.textContent = '•';
      label.appendChild(flag);
      row.appendChild(label);

      const inputs = document.createElement('div');
      inputs.className = 'control-inputs';

      let slider = null;
      let box;
      if (control.kind === 'choice') {
        box = document.createElement('select');
        box.hidden = true;
        slider = document.createElement('input');slider.type='range';slider.id=id;slider.min=0;slider.max=control.choices.length-1;slider.step=1;slider.className='weight-slider';slider.setAttribute('aria-label',control.label+' weight');
        slider.style.setProperty('--steps',control.choices.length-1);
        slider.addEventListener('input',()=>{box.value=control.choices[Number(slider.value)];onChange(control,box.value);});inputs.append(slider);
        const legend=document.createElement('div');legend.className='weight-legend';
        for(const [i,weight] of control.choices.entries()){const mark=document.createElement('span');mark.textContent=weight;legend.append(mark);}
        row.append(legend);
        for (const choice of control.choices) {
          const option = document.createElement('option');
          option.value = choice;
          option.textContent = choice;
          box.appendChild(option);
        }
        box.addEventListener('change', () => onChange(control, box.value));
      } else {
        slider = document.createElement('input');
        slider.type = 'range';
        slider.min = control.min;
        slider.max = control.max;
        slider.step = control.step;
        slider.style.setProperty('--steps',Math.min(40,Math.round((control.max-control.min)/control.step)));
        slider.setAttribute('aria-label', `${control.label} slider`);
        slider.addEventListener('input', () => {
          box.value = slider.value;
          onChange(control, Number(slider.value));
        });
        inputs.appendChild(slider);

        box = document.createElement('input');
        box.type = 'number';
        box.id = id;
        box.step = control.step;
        // Deliberately no min/max on the box: the slider's range is a
        // convenience, and the validator — not this panel — decides what a legal
        // value is. Typing 24 pt into a slider that stops at 18 must work.
        box.addEventListener('change', () => {
          const value = Number(box.value);
          if (Number.isFinite(value)) onChange(control, value);
        });
      }
      inputs.appendChild(box);

      if (control.kind !== 'choice') {
        const unit = document.createElement('span');
        unit.className = 'control-unit';
        unit.textContent = control.unit || '';
        inputs.appendChild(unit);
      }

      const reset = document.createElement('button');
      reset.type = 'button';
      reset.className = 'control-reset';
      reset.textContent = 'Reset';
      reset.title = `Reset ${control.label} to the profile value`;
      reset.addEventListener('click', () => onReset(control));
      inputs.appendChild(reset);

      row.insertBefore(inputs,row.querySelector('.weight-legend'));
      if(control.kind !== 'choice'){const ticks=document.createElement('div');ticks.className='range-legend';ticks.innerHTML=`<span>${control.min}</span><span>${control.max}${control.unit?' '+control.unit:''}</span>`;row.append(ticks);}

      const reason = document.createElement('p');
      reason.className = 'control-reason';
      reason.hidden = true;
      row.appendChild(reason);

      section.appendChild(row);
      registry.set(control.path, { control, row, slider, box, flag, reason });
    }
    root.appendChild(section);
  }

  return {
    /**
     * Push the current profile into the widgets and say which of them apply.
     *
     * A control that cannot affect *this* spec is disabled and given a reason,
     * rather than left live and inert: bar settings on a line chart, title
     * settings on a spec with no title.
     */
    sync(profile, baseProfile, spec) {
      const kind = (spec && spec.kind) || 'line';
      const hasTitle = spec?.kind === 'grid' ? spec.panels.some(p => Boolean(p.title?.trim())) : Boolean(spec && typeof spec.title === 'string' && spec.title.trim());
      for(const section of root.querySelectorAll('[data-kinds]'))section.hidden=!section.dataset.kinds.split(',').some(k=>spec?.kind==='grid'?spec.panels.some(p=>p.kind===k):kind===k);
      for (const { control, row, slider, box, flag, reason } of registry.values()) {
        const value = effectiveValue(profile, control);
        if (value !== undefined) {
          if (slider) {slider.value = control.kind==='choice'?String(control.choices.indexOf(value)):String(value);slider.setAttribute('aria-valuetext',String(value));slider.style.setProperty('--fill',`${(Number(slider.value)-Number(slider.min))/(Number(slider.max)-Number(slider.min))*100}%`);}
          box.value = String(value);
        }
        const changed = isOverridden(profile, baseProfile, control);
        row.classList.toggle('is-overridden', changed);
        flag.hidden = !changed;

        let why = '';
        if ((control.kinds || control.groupKinds) && !(spec?.kind === 'grid' ? spec.panels.some(p => (control.kinds || control.groupKinds).includes(p.kind)) : (control.kinds || control.groupKinds).includes(kind))) {
          why = `only applies to ${(control.kinds || control.groupKinds).join(' and ')} charts`;
        } else if (control.requiresTitle && !hasTitle) {
          why = 'this spec has no title, so this would change nothing';
        }
        const applies = why === '';
        row.classList.toggle('is-inapplicable', !applies);
        row.hidden=!applies;
        reason.textContent = why;
        reason.hidden = applies;
        if (slider) slider.disabled = !applies;
        box.disabled = !applies;
      }
    },
    registry,
  };
}
