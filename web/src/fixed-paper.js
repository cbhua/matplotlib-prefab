/** Fixed-page reproduction experiment: HTML text with measured, frozen line breaks.
 * The PDF was measured once offline. No PDF renderer, TeX, or Python runs here.
 * Text widths remain native font advances: never stretch text to pass a comparison.
 */
const PX_PER_PT = 96 / 72;
const NS = 'http://www.w3.org/2000/svg';
const px = pt => `${pt * PX_PER_PT}px`;
function svg(tag, attrs) {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}
export function renderFixedPaper(page) {
  const paper = document.createElement('article');
  paper.className = 'fixed-paper';
  paper.setAttribute('aria-label', 'ICML reference page reproduced with HTML text');
  paper.style.width = px(page.paper.width_pt);
  paper.style.height = px(page.paper.height_pt);
  const byIndex = new Map(page.runs.map(run => [run.index, run]));
  // Preserve the extractor's complete blocks, including bibliography lines near
  // the footer. Region heuristics must never discard any content on this page.
  const blocks = [...page.blocks].sort((a, b) => a.column - b.column
    || b.lines[0].baseline_pt - a.lines[0].baseline_pt);
  for (const block of blocks) {
    const group = document.createElement('section');
    group.className = 'fixed-block'; group.dataset.kind = block.kind;
    group.dataset.region = block.region; group.dataset.column = block.column;
    for (const line of block.lines) {
      const row = document.createElement('div'); row.className = 'fixed-line';
      for (const index of line.runs) {
        const run = byIndex.get(index);
        if (run.mode === 'outline') {
          // Only the small Computer Modern formula fragments use vector paths;
          // the body, citations, bibliography, header and folio are HTML text.
          const math = svg('svg', {class: 'fixed-math', 'data-index': index,
            width: px(page.paper.width_pt), height: px(page.paper.height_pt),
            viewBox: `0 0 ${page.paper.width_pt} ${page.paper.height_pt}`,
            role: 'img', 'aria-label': `maths: ${run.text}`});
          for (const glyph of run.glyphs) {
            const outline = page.outline_glyphs[glyph.key];
            const scale = run.size_pt / outline.units_per_em;
            math.append(svg('path', {d: outline.path,
              transform: `translate(${glyph.x_pt} ${page.paper.height_pt - run.baseline_pt}) scale(${scale} ${-scale})`}));
          }
          row.append(math); continue;
        }
        const node = document.createElement('span');
        node.className = 'fixed-run'; node.dataset.index = index;
        Object.assign(node.style, {left: px(run.x_pt), top: px(page.paper.height_pt - run.baseline_pt),
          fontFamily: `"${run.css_family}"`, fontSize: px(run.size_pt),
          fontWeight: run.weight, fontStyle: run.style});
        node.append(document.createTextNode(run.text));
        const marker = document.createElement('i'); marker.className = 'baseline-marker';
        marker.setAttribute('aria-hidden', 'true'); node.append(marker);
        row.append(node);
      }
      group.append(row);
    }
    paper.append(group);
  }
  for (const rule of page.rules) {
    const node = document.createElement('div'); node.className = 'fixed-rule';
    Object.assign(node.style, {left: px(rule.x_pt), top: px(page.paper.height_pt - rule.y_pt - rule.height_pt),
      width: px(rule.width_pt), height: px(rule.height_pt)});
    paper.append(node);
  }
  const slot = document.createElement('div'); slot.className = 'fixed-slot';
  Object.assign(slot.style, {left: px(page.slot.x_pt), top: px(page.slot.top_pt),
    width: px(page.slot.width_pt), height: px(page.slot.height_pt)});
  paper.append(slot);
  return paper;
}

export async function alignFixedBaselines(paper) {
  await document.fonts.ready;
  // A zero-height inline marker exposes the actual HTML baseline. Read all
  // offsets before writing transforms, avoiding one layout pass per text run.
  const offsets = [...paper.querySelectorAll('.fixed-run')].map(node =>
    [node, node.querySelector('.baseline-marker').getBoundingClientRect().top - node.getBoundingClientRect().top]);
  for (const [node, offset] of offsets) node.style.transform = `translateY(${-offset}px)`;
}

export function measureFixedPaper(paper, page) {
  const origin = paper.getBoundingClientRect();
  const toPt = 72 / 96;
  const rect = node => {
    const r = node.getBoundingClientRect();
    return {x_pt: (r.left - origin.left) * toPt, top_pt: (r.top - origin.top) * toPt,
      width_pt: r.width * toPt, height_pt: r.height * toPt};
  };
  return {
    paper: rect(paper), slot: rect(paper.querySelector('.fixed-slot')),
    runs: [...paper.querySelectorAll('.fixed-run')].map(node => {
      const range = document.createRange(); range.selectNodeContents(node.firstChild);
      const r = range.getBoundingClientRect();
      return {index: Number(node.dataset.index), text: node.firstChild.textContent,
        x_pt: (r.left - origin.left) * toPt, width_pt: r.width * toPt,
        baseline_pt: page.paper.height_pt - (node.querySelector('.baseline-marker').getBoundingClientRect().top - origin.top) * toPt,
        family: getComputedStyle(node).fontFamily, size_pt: parseFloat(getComputedStyle(node).fontSize) * toPt};
    }),
    math: [...paper.querySelectorAll('.fixed-math')].map(node => Number(node.dataset.index)),
    lines: paper.querySelectorAll('.fixed-line').length,
  };
}
