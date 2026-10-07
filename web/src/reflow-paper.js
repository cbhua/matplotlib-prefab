import { renderPaperPage } from './css-paper.js';
import { renderFixedPaper, alignFixedBaselines } from './fixed-paper.js';
const px = pt => `${pt * 96 / 72}px`;
const mmPx = mm => mm * 96 / 25.4;

export function contentBlocks(body, references) {
  const blocks = body.split(/\n\s*\n/).filter(s => s.trim()).map(text => ({
    kind: text.trim().startsWith('## ') ? 'heading' : 'paragraph',
    segments: [{text: text.trim().replace(/^## /, '')}],
  }));
  if (references.length) blocks.push({kind: 'heading', segments: [{text: 'References'}]},
    ...references.map(r => ({kind: 'reference', segments: r.segments})));
  return blocks.map((block, index) => {
    // Preserve inline styles while splitting only at word boundaries. PDF text
    // runs may split a word into several pieces; they must remain one token.
    const tokens = []; let word = [];
    for (const segment of block.segments) {
      for (const part of segment.text.split(/(\s+)/)) {
        if (!part) continue;
        if (/^\s+$/.test(part)) { if (word.length) tokens.push(word); word = []; }
        else word.push({...segment, text: part});
      }
    }
    if (word.length) tokens.push(word);
    return {...block, index, tokens};
  });
}

function fill(node, tokens, start, end) {
  node.replaceChildren();
  tokens.slice(start, end).forEach((word, i) => {
    if (i) node.append(' ');
    for (const part of word) {
      const span = document.createElement(part.italic ? 'em' : 'span');
      span.textContent = part.text; node.append(span);
    }
  });
  node.dataset.start = start; node.dataset.end = end;
}

/** Browser line breaking plus measured column/page fragmentation. No hidden prose. */
export async function paginatePaper(host, source, blocks, config) {
  const {heightMm, wide, caption, imageUrl} = config;
  if (!Number.isFinite(heightMm) || heightMm < 10 || heightMm > 180) throw Error('Figure height must be between 10 and 180 mm.');
  const scratch = document.createElement('div'); scratch.className = 'reflow-measure';
  scratch.setAttribute('aria-hidden', 'true'); document.body.append(scratch);
  const pages = [], columns = []; let current = 0;
  const base = source.text_block;
  const columnCount = source.venue.columns;
  const wrap = Boolean(source.layout.text_wrap);
  const settings = source.preview_settings;
  const figureWidth = source.runs ? (wide ? base.width_mm : base.column_width_mm) : source.figure.width_mm;
  const headerRuns = (source.runs || []).filter(r => r.region === 'header' || (r.region === 'footer' && /^\d+$/.test(r.text)));
  const ids = new Set(headerRuns.map(r => r.index));
  const chrome = {...source, runs: headerRuns, rules: (source.rules || []).filter(r => r.y_pt > 730),
    blocks: (source.blocks || []).filter(b => b.lines.every(l => l.runs.every(i => ids.has(i))))};
  function addPage() {
    const page = source.runs ? renderFixedPaper(chrome) : renderPaperPage(source).paper;
    page.classList.add('reflow-paper');
    page.dataset.textWrap = String(wrap);
    page.querySelector('.fixed-slot')?.remove();
    const flowBody = page.querySelector('.css-paper-body');
    if (flowBody) flowBody.replaceChildren();
    const footer = page.querySelector('.css-paper-footer');
    if (footer) footer.textContent = String(2 + pages.length);
    for (const n of page.querySelectorAll('.fixed-run')) {
      if (/^\d+$/.test(n.firstChild.textContent)) n.firstChild.textContent = String(2 + pages.length);
    }
    let reserve = 0;
    if (!pages.length) {
      const figure = document.createElement('figure'); figure.className = 'reflow-figure';
      Object.assign(figure.style, {left: `${base.left_mm}mm`, top: `${source.slot.top_pt * 25.4 / 72}mm`,
        width: `${figureWidth}mm`});
      const slot = document.createElement('div'); slot.className = 'reflow-slot mpf-slot'; slot.style.height = `${heightMm}mm`;
      if (imageUrl) { const img = document.createElement('img'); img.src = imageUrl; img.alt = 'Uploaded figure'; slot.append(img); }
      const label = document.createElement('span'); label.className = 'slot-size';
      label.textContent = `${figureWidth.toFixed(2)} × ${heightMm.toFixed(2)} mm`;
      if (config.showDimensions !== false) slot.append(label);
      const cap = document.createElement('figcaption'); cap.textContent = caption;
      if (settings) cap.style.fontSize = `${settings.caption_size_pt}pt`;
      figure.append(slot, cap); page.append(figure);
    }
    scratch.append(page);
    if (!pages.length) reserve = page.querySelector('.reflow-figure').getBoundingClientRect().height + mmPx(6);
    const pageTop = source.slot.top_pt * 96 / 72;
    const bodyBottom = mmPx(base.top_mm + base.height_mm);
    if (config.maxPages !== 1 && reserve > bodyBottom - pageTop - 32) throw Error('Figure and caption leave too little space for text. Reduce their height or shorten the caption.');
    for (let col = 0; col < columnCount; col++) {
      const column = document.createElement('div'); column.className = 'reflow-column';
      const top = pageTop + ((!pages.length && !wrap && (col === 0 || wide)) ? reserve : 0);
      Object.assign(column.style, {left: `${base.left_mm + col * (base.column_width_mm + base.column_gap_mm)}mm`,
        top: `${top}px`, width: `${base.column_width_mm}mm`, height: `${Math.max(0,bodyBottom - top)}px`});
      column.dataset.column = col; column.dataset.page = pages.length;
      if (settings) {
        column.style.fontSize = `${settings.body_size_pt}pt`;
        column.style.lineHeight = `${settings.body_leading_pt}pt`;
        column.style.setProperty('--paragraph-gap', `${settings.paragraph_gap_pt}pt`);
      }
      if (flowBody) {
        column.style.left = `${col * (base.column_width_mm + base.column_gap_mm)}mm`;
        column.style.top = `${top - mmPx(base.top_mm)}px`;
        flowBody.append(column);
      } else page.append(column);
      if (!pages.length && col === 0 && wrap) {
        const figure = page.querySelector('.reflow-figure');
        figure.classList.add('mpf-wrapped-figure');
        Object.assign(figure.style, {position: 'relative', left: 'auto', top: 'auto', float: 'right',
          margin: `0 0 9pt ${settings?.wrap_gap_mm ?? 3.5}mm`});
        column.append(figure);
      }
      columns.push(column);
    }
    pages.push(page);
  }
  const fits = column => column.scrollHeight <= column.clientHeight + .5 && column.scrollWidth <= column.clientWidth + .5;
  function nextColumn() { current++; if (!columns[current]) {if(pages.length >= (config.maxPages ?? Infinity))return false;addPage();} return true; }
  try {
    // Explicitly load all body faces before measuring even if the fixed header
    // only needed bold. No later fallback-font swap may invalidate pagination.
    await Promise.all(['normal', 'italic'].map(style => document.fonts.load(`${style} 10pt "MPF Nimbus Roman"`)));
    await document.fonts.load('bold 12pt "MPF Nimbus Roman"');
    addPage();
    flow: for (const block of blocks) {
      let start = 0;
      while (start < block.tokens.length) {
        let column = columns[current];
        const node = document.createElement(block.kind === 'heading' ? 'h2' : 'p');
        node.className = `flow-fragment ${block.kind}`; node.dataset.block = block.index;
        if (start) node.classList.add('continuation');
        fill(node, block.tokens, start, block.tokens.length); column.append(node);
        // Keep headings with at least two following body lines.
        const headingFits = block.kind !== 'heading' || node.getBoundingClientRect().bottom + 40 <= column.getBoundingClientRect().bottom;
        if (fits(column) && headingFits) break;
        if (block.kind === 'heading') {
          node.remove();
          if (!column.children.length && column.clientHeight > 200) throw Error('A heading is too long for a column. Shorten it or use a paragraph.');
          if(!nextColumn())break flow; continue;
        }
        let lo = start, hi = block.tokens.length;
        while (lo < hi) {
          const mid = Math.ceil((lo + hi) / 2); fill(node, block.tokens, start, mid);
          if (fits(column)) lo = mid; else hi = mid - 1;
        }
        fill(node, block.tokens, start, lo);
        // Do not strand a single line at the foot of a column. Try the next
        // column; a full column always has room for at least one text line.
        if (lo === start || (node.getBoundingClientRect().height < 30 && column.children.length > 1)) {
          node.remove();
          if (lo === start && !column.children.length && column.clientHeight > 700) throw Error('A single word is too large for a column. Add a space to split it.');
          if(!nextColumn())break flow; continue;
        }
        start = lo;
        node.classList.add('split-end');
        if(!nextColumn())break flow;
      }
    }
    if (source.runs) await Promise.all(pages.map(alignFixedBaselines));
    if (config.shouldCommit && !config.shouldCommit()) return null;
    host.replaceChildren(...pages);
    return {pages: pages.length, columns: columns.length, heightMm,
      widthMm: figureWidth,
      words: blocks.reduce((n, block) => n + block.tokens.length, 0)};
  } finally { scratch.remove(); }
}
