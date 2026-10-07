/**
 * Build the paper page from a generated baseline manifest.
 * For browser text-wrap previews, keep the header/folio and measured dimensions
 * while wrap-layout.js lays out illustrative prose around the figure.
 *
 * Nothing in here decides where anything goes. Every position, size, face and
 * line break comes from `page.json`, which was measured off a compiled LaTeX
 * page. This module's whole job is to put those numbers on screen without
 * rounding them, and to leave one hole in the page for the live figure.
 *
 * Coordinates
 * -----------
 * The page's internal coordinate system is PDF points (72 per inch), the units
 * the measurements are in, with y counted down from the top. The paper element
 * is sized in CSS pixels (96 per inch), so one point is 96/72 px, and a display
 * zoom is applied as a transform on a wrapper — never by changing a coordinate,
 * so no exported number can be contaminated by how big the preview looks.
 *
 * Why the text is SVG rather than positioned spans
 * ------------------------------------------------
 * A run has to sit on a measured baseline. CSS gives no way to say "put this
 * text's baseline here": the offset from a positioned box's top to the baseline
 * depends on the strut, the line-height and the font's own ascent metrics, so
 * an HTML span would have to be nudged by a number derived from the font rather
 * than from the page. `<text y=…>` *is* the baseline, by specification. The text
 * is still real text — selectable, copyable, in reading order, set in the actual
 * font — which is what the page needs it to be.
 */

import { mountWrappedBody } from './wrap-layout.js';

const PT_TO_PX = 96 / 72;
const SVG_NS = 'http://www.w3.org/2000/svg';

/** Order the DOM so that selecting the page yields prose, not a jumble. */
function blocksInReadingOrder(page) {
  const rank = { header: 0, body: 1, footer: 2 };
  return [...page.blocks].sort((a, b) => {
    const region = rank[a.region] - rank[b.region];
    if (region !== 0) return region;
    if (a.column !== b.column) return a.column - b.column;
    return b.lines[0].baseline_pt - a.lines[0].baseline_pt;
  });
}

function svg(tag, attributes = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (value !== null && value !== undefined) node.setAttribute(name, String(value));
  }
  return node;
}

/**
 * One measured run. Text runs become <text>; runs in a font the site does not
 * package (the Computer Modern maths) become the outlines taken from the
 * baseline PDF's own embedded font program.
 */
function renderRun(run, page) {
  const height = page.paper.height_pt;
  if (run.mode === 'outline') {
    const group = svg('g', { class: 'mpf-run mpf-run-outline', 'data-index': run.index });
    // Not selectable text: say so, rather than letting a screen reader announce
    // a path as if it were a word.
    group.setAttribute('role', 'img');
    group.setAttribute('aria-label', `maths: ${run.text}`);
    for (const glyph of run.glyphs) {
      const outline = page.outline_glyphs[glyph.key];
      if (!outline) continue;
      const scale = run.size_pt / outline.units_per_em;
      group.appendChild(svg('path', {
        d: outline.path,
        transform: `translate(${glyph.x_pt} ${height - run.baseline_pt}) scale(${scale} ${-scale})`,
      }));
    }
    return group;
  }
  const node = svg('text', {
    class: 'mpf-run',
    'data-index': run.index,
    x: run.x_pt,
    y: height - run.baseline_pt,
    'font-family': run.css_family,
    'font-size': run.size_pt,
    'font-weight': run.weight,
    'font-style': run.style,
    'xml:space': 'preserve',
  });
  node.textContent = run.text;
  return node;
}

/**
 * Draw the page. Returns the elements the app needs to talk to afterwards.
 *
 * `options.showSlotOutline` draws the empty slot's edge, which is what the
 * baseline PDF has in it; the app turns it off once a real figure is in place.
 */
export function renderPaperPage(page, options = {}) {
  const widthPx = page.paper.width_pt * PT_TO_PX;
  const heightPx = page.paper.height_pt * PT_TO_PX;

  const paper = document.createElement('div');
  paper.className = 'mpf-paper';
  paper.style.width = `${widthPx}px`;
  paper.style.height = `${heightPx}px`;
  paper.setAttribute('data-venue', page.venue.id);
  paper.setAttribute('data-layout', page.layout.id);
  const wrapped = page.layout.preview_engine === 'browser-text-flow';
  paper.dataset.textWrap = String(wrapped);

  const sheet = svg('svg', {
    class: 'mpf-sheet',
    width: widthPx,
    height: heightPx,
    viewBox: `0 0 ${page.paper.width_pt} ${page.paper.height_pt}`,
    'aria-hidden': 'false',
  });
  sheet.setAttribute('role', 'document');

  // TeX's rules: the running head's line, and anything else the template draws.
  // The slot's own placeholder edge is not among these — the slot is a hole.
  const rules = svg('g', { class: 'mpf-rules', 'aria-hidden': 'true' });
  for (const rule of page.rules) {
    rules.appendChild(svg('rect', {
      x: rule.x_pt,
      y: page.paper.height_pt - (rule.y_pt + rule.height_pt),
      width: rule.width_pt,
      height: rule.height_pt,
    }));
  }
  sheet.appendChild(rules);

  const byIndex = new Map(page.runs.map((run) => [run.index, run]));
  for (const block of blocksInReadingOrder(page)) {
    if (wrapped && block.region === 'body') continue;
    // The source extractor can classify the last bibliography line as footer.
    // In reflow mode retain the folio, not fragments from the replaced prose.
    if (wrapped && block.region === 'footer' && !/^\d+$/.test(block.text.trim())) continue;
    const group = svg('g', {
      class: `mpf-block mpf-block-${block.kind}`,
      'data-kind': block.kind,
      'data-region': block.region,
      'data-column': block.column,
    });
    for (const line of block.lines) {
      const lineGroup = svg('g', { class: 'mpf-line' });
      for (const index of line.runs) {
        const run = byIndex.get(index);
        if (run) lineGroup.appendChild(renderRun(run, page));
      }
      group.appendChild(lineGroup);
    }
    sheet.appendChild(group);
  }
  paper.appendChild(sheet);

  const slot = document.createElement('div');
  slot.className = 'mpf-slot';
  slot.style.left = `${page.slot.x_pt * PT_TO_PX}px`;
  slot.style.top = `${page.slot.top_pt * PT_TO_PX}px`;
  slot.style.width = `${page.slot.width_pt * PT_TO_PX}px`;
  slot.style.height = `${page.slot.height_pt * PT_TO_PX}px`;
  slot.setAttribute('role', 'img');
  slot.setAttribute('aria-label',
    `Figure slot, ${page.slot.width_mm.toFixed(2)} by ${page.slot.height_mm.toFixed(2)} millimetres`);
  if (options.showSlotOutline) slot.classList.add('mpf-slot-empty');
  if (wrapped) mountWrappedBody(paper, slot, page);
  else paper.appendChild(slot);

  return { paper, sheet, slot, widthPx, heightPx };
}

export { setFigure, clearFigure, fontFaceCss } from './figure-view.js';

export const POINTS_TO_PIXELS = PT_TO_PX;
