/** Single-column articles: a half-text-width figure floated to the right.
 * Template dimensions and fonts are measured; browser line breaking is a preview,
 * not a newly calibrated LaTeX page. Keep the original baseline assets intact.
 */
import { PARAGRAPHS } from './paper-prose.js';

const MM_TO_PT = 72 / 25.4;

export function usesTextWrap(page) {
  return page.venue.columns === 1 && page.layout.id === 'narrow';
}

export function withTextWrap(source) {
  if (!usesTextWrap(source)) return source;
  const page = structuredClone(source);
  page.layout.label = 'half the text width · text wrap';
  page.layout.float_environment = 'wrapfigure';
  page.layout.placement = 'right';
  page.layout.preview_engine = 'browser-text-flow';
  page.layout.target_width_rule = '0.5 * textwidth';
  page.layout.note = 'Half the text width, on the right, with body text wrapping on the left and below.';
  page.note = 'Browser text-wrap preview using the source template dimensions and fonts. Text positions are not LaTeX-calibrated.';
  page.provenance.preview_transform = 'web/src/wrap-layout.js; original illustrative prose and browser line breaking';
  const { text_block: block, slot } = page;
  slot.width_mm = page.figure.width_mm;
  slot.height_mm = page.figure.height_mm;
  slot.width_pt = slot.width_mm * MM_TO_PT;
  slot.height_pt = slot.height_mm * MM_TO_PT;
  slot.x_pt = block.right_mm * MM_TO_PT - slot.width_pt;
  slot.top_pt = block.top_mm * MM_TO_PT;
  slot.y_pt = page.paper.height_pt - slot.top_pt - slot.height_pt;
  slot.note = 'Figure size follows the measured template width. The position and surrounding text are browser-reflowed.';
  return page;
}

// Original illustrative prose, deliberately free of claims about actual results.
// These paragraphs provide uninterrupted text for wrapping around the figure.


export function mountWrappedBody(paper, slot, page) {
  const px = mm => mm * 96 / 25.4;
  const texPx = pt => pt * 96 / 72.27;
  const body = document.createElement('div');
  body.className = 'mpf-wrapped-body';
  body.lang = 'en';
  const block = page.text_block;
  Object.assign(body.style, {
    left: `${px(block.left_mm)}px`, top: `${px(block.top_mm)}px`,
    width: `${px(block.width_mm)}px`, height: `${px(block.height_mm)}px`,
    fontSize: `${texPx(page.template.body_font_size_pt)}px`,
    lineHeight: `${texPx(page.template.body_baselineskip_tex_pt)}px`,
  });
  const face = page.runs.find(run => run.region === 'body' && run.mode === 'text' && run.weight === 'normal');
  if (face) body.style.fontFamily = `"${face.css_family}", serif`;
  const figure = document.createElement('figure');
  figure.className = 'mpf-wrapped-figure';
  figure.style.width = `${px(page.figure.width_mm)}px`;
  figure.style.marginLeft = `${px(page.template.columnsep_mm)}px`;
  // The slot remains at its original physical size inside the float.
  Object.assign(slot.style, { position: 'relative', left: '0', top: '0' });
  const caption = document.createElement('figcaption');
  caption.textContent = 'Figure 1: Synthetic example data, shown at half the text width. The surrounding text is illustrative context for this layout preview.';
  caption.style.fontSize = `${texPx(page.template.caption_font_size_pt)}px`;
  caption.style.lineHeight = `${texPx(page.template.caption_baselineskip_tex_pt)}px`;
  figure.append(slot, caption);
  body.append(figure);
  for (const text of PARAGRAPHS) {
    const p = document.createElement('p');
    p.textContent = text;
    p.style.marginBottom = `${texPx(page.template.margins_tex_pt.parskip || 6)}px`;
    body.append(p);
  }
  paper.append(body);
}
