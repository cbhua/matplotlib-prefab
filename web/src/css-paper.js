/** Pure browser paper proportions. This module has no compiled-page dependency. */
import { PARAGRAPHS } from './paper-prose.js';

export const PAPER_CONTROLS = [
  { key: 'body_size_pt', label: 'Body text', unit: 'pt', min: 6, max: 18, step: 'any' },
  { key: 'body_leading_pt', label: 'Body line height', unit: 'pt', min: 8, max: 28, step: 'any' },
  { key: 'caption_size_pt', label: 'Caption text', unit: 'pt', min: 6, max: 16, step: 'any' },
  { key: 'paragraph_gap_pt', label: 'Paragraph spacing', unit: 'pt', min: 0, max: 16, step: 'any' },
  { key: 'wrap_gap_mm', label: 'Text wrap gap', unit: 'mm', min: 1, max: 12, step: 'any' },
];

function positive(value, name) {
  if (!Number.isFinite(value) || value <= 0) throw new Error(`Paper preset: ${name} must be positive.`);
}

export function validatePresets(catalog) {
  if (catalog.schema_version !== '1' || !Array.isArray(catalog.presets) || !catalog.presets.length) {
    throw new Error('Paper presets need schema_version 1 and a non-empty presets array.');
  }
  const ids = new Set();
  for (const p of catalog.presets) {
    if (!/^[a-z0-9-]+$/.test(p.id) || ids.has(p.id)) throw new Error('Paper preset IDs must be unique.');
    ids.add(p.id);
    if (![1, 2].includes(p.columns)) throw new Error(`${p.id}: use one or two article columns.`);
    for (const key of ['width_mm', 'height_mm']) {
      positive(p.paper[key], `paper.${key}`); positive(p.body[key], `body.${key}`);
    }
    for (const key of ['left_mm', 'top_mm']) {
      if (!Number.isFinite(p.body[key]) || p.body[key] < 0) throw new Error(`${p.id}: invalid ${key}.`);
    }
    if (p.body.left_mm + p.body.width_mm > p.paper.width_mm
        || p.body.top_mm + p.body.height_mm > p.paper.height_mm) throw new Error(`${p.id}: body must fit on paper.`);
    if (typeof p.font_family !== 'string' || !p.font_family.trim()) throw new Error(`${p.id}: missing font family.`);
    positive(p.figure_aspect_ratio, 'figure_aspect_ratio');
    positive(p.column_gap_mm, 'column_gap_mm');
    if (p.column_gap_mm >= p.body.width_mm) throw new Error(`${p.id}: column gap is too large.`);
    for (const control of PAPER_CONTROLS) {
      const value = p[control.key];
      if (!Number.isFinite(value) || value < control.min || value > control.max) {
        throw new Error(`${p.id}: ${control.key} must be between ${control.min} and ${control.max}.`);
      }
    }
  }
  return catalog;
}

export function createPage(preset, layout, overrides = {}) {
  if (!['narrow', 'wide'].includes(layout)) throw new Error(`Unknown paper width: ${layout}`);
  const settings = Object.fromEntries(PAPER_CONTROLS.map(c => [c.key, overrides[c.key] ?? preset[c.key]]));
  const wrap = preset.columns === 1 && layout === 'narrow';
  const width = overrides.figure_width_mm ?? (layout === 'wide' ? preset.body.width_mm
    : preset.columns === 1 ? preset.body.width_mm / 2 : (preset.body.width_mm - preset.column_gap_mm) / 2);
  const height = overrides.figure_height_mm ?? width * preset.figure_aspect_ratio;
  const spansColumns=preset.columns===2 && width>(preset.body.width_mm-preset.column_gap_mm)/2+.01;
  const left = preset.body.left_mm + (wrap ? preset.body.width_mm - width : 0);
  const pt = value => value * 72 / 25.4;
  return {
    schema_version: '1',
    venue: { id: preset.id, name: preset.name, year: preset.year, columns: preset.columns, mode: 'proportion reference' },
    layout: { id: layout, label: wrap ? 'half the text width · text wrap'
      : layout === 'wide' ? (preset.columns === 2 ? 'both columns' : 'the full text width') : 'one column',
    float_environment: wrap ? 'wrapfigure' : spansColumns ? 'figure*' : 'figure',
    placement: wrap ? 'right' : 'top', text_wrap: wrap, preview_engine: 'css-paper',
    target_width_rule: overrides.figure_width_mm!==undefined ? 'explicit physical width' : layout === 'wide' ? 'textwidth' : wrap ? '0.5 * textwidth' : 'columnwidth' },
    paper: { ...preset.paper, width_pt: pt(preset.paper.width_mm), height_pt: pt(preset.paper.height_mm) },
    text_block: { ...preset.body, column_gap_mm: preset.column_gap_mm, columns: preset.columns,
      right_mm: preset.body.left_mm + preset.body.width_mm,
      column_width_mm: (preset.body.width_mm - (preset.columns - 1) * preset.column_gap_mm) / preset.columns },
    figure: { width_mm: width, height_mm: height },
    slot: { width_mm: width, height_mm: height, width_pt: pt(width), height_pt: pt(height), x_pt: pt(left), top_pt: pt(preset.body.top_mm) },
    template: { body_font_size_pt: settings.body_size_pt, caption_font_size_pt: settings.caption_size_pt,
      columns: preset.columns, columnsep_mm: preset.column_gap_mm },
    preview_settings: settings, preset: structuredClone(preset),
    provenance: { source: 'presets/papers.json', engine: 'native HTML/CSS', accuracy: 'proportional reference, not LaTeX-equivalent' },
  };
}

export function templateIndex(catalog) {
  return { pages: catalog.presets.flatMap(preset => ['narrow', 'wide'].map(layout => {
    const p = createPage(preset, layout);
    return { venue: preset.id, name: preset.name, columns: preset.columns, layout,
      label: p.layout.label, float_environment: p.layout.float_environment,
      figure_width_mm: p.figure.width_mm, figure_height_mm: p.figure.height_mm };
  })) };
}

function element(tag, className, text) {
  const node = document.createElement(tag); node.className = className;
  if (text) node.textContent = text;
  return node;
}

export function applyPaperSettings(paper, page) {
  const s = page.preview_settings;
  for (const [key, value] of Object.entries(s)) {
    paper.style.setProperty(`--${key.replaceAll('_', '-')}`, `${value}${key.endsWith('_mm') ? 'mm' : 'pt'}`);
  }
  const slot = paper.querySelector('.mpf-slot');
  slot.style.width = `${page.figure.width_mm}mm`;
  slot.style.height = `${page.figure.height_mm}mm`;
}

/** Only sample prose is fitted; charts are never silently resized to fit. */
export function fitSampleProse(paper) {
  const body = paper.querySelector('.css-paper-body');
  const paragraphs = [...body.querySelectorAll('.sample-prose')];
  paragraphs.forEach(p => { p.hidden = false; });
  const overflows = () => body.scrollHeight > body.clientHeight + 1 || body.scrollWidth > body.clientWidth + 1;
  for (let i = paragraphs.length - 1; i >= 0 && overflows(); i--) paragraphs[i].hidden = true;
  paper.dataset.overflow = String(overflows());
  return !overflows();
}

export function renderPaperPage(page, options = {}) {
  const paper = element('article', 'mpf-paper css-paper');
  paper.dataset.venue = page.venue.id; paper.dataset.layout = page.layout.id;
  paper.dataset.columns = page.venue.columns; paper.dataset.textWrap = String(page.layout.text_wrap);
  paper.dataset.engine = 'css-paper';
  paper.style.width = `${page.paper.width_mm}mm`; paper.style.height = `${page.paper.height_mm}mm`;
  paper.style.fontFamily = `"${page.preset.font_family}", serif`;
  const header = element('header', 'css-paper-header', page.preset.running_header);
  Object.assign(header.style, { left: `${page.text_block.left_mm}mm`, width: `${page.text_block.width_mm}mm`,
    top: `${Math.max(4, page.text_block.top_mm - 12)}mm` });
  const body = element('div', `css-paper-body${page.layout.text_wrap ? ' mpf-wrapped-body' : ''}`);
  Object.assign(body.style, { left: `${page.text_block.left_mm}mm`, top: `${page.text_block.top_mm}mm`,
    width: `${page.text_block.width_mm}mm`, height: `${page.text_block.height_mm}mm`,
    columnCount: String(page.venue.columns), columnGap: `${page.preset.column_gap_mm}mm` });
  const figure = element('figure', `css-paper-figure${page.layout.text_wrap ? ' mpf-wrapped-figure' : ''}`);
  if (page.layout.text_wrap) figure.style.width = `${page.figure.width_mm}mm`;
  else if (page.venue.columns === 2 && page.layout.id === 'wide') figure.style.columnSpan = 'all';
  const slot = element('div', 'mpf-slot');
  if (options.showSlotOutline) slot.classList.add('mpf-slot-empty');
  slot.setAttribute('role', 'img'); slot.setAttribute('aria-label', `Figure at ${page.figure.width_mm.toFixed(2)} mm wide`);
  const caption = element('figcaption', 'css-paper-caption', 'Figure 1. Synthetic example data. This page illustrates the figure’s proportions alongside the surrounding text.');
  figure.append(slot, caption); body.append(figure);
  for (const text of PARAGRAPHS) body.append(element('p', 'sample-prose', text));
  paper.append(header, body, element('footer', 'css-paper-footer', '3'));
  applyPaperSettings(paper, page);
  return { paper, slot, widthPx: page.paper.width_mm * 96 / 25.4, heightPx: page.paper.height_mm * 96 / 25.4 };
}
