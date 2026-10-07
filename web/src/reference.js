import { renderFixedPaper, alignFixedBaselines, measureFixedPaper } from './fixed-paper.js';
import { fontFaceCss } from './figure-view.js';
const base = './public/generated/';
try {
  const [page, fonts, supplement] = await Promise.all([
    fetch(`${base}conferences/icml2026/narrow/page.json`).then(r => { if (!r.ok) throw Error('Missing fixed page'); return r.json(); }),
    fetch(`${base}fonts/fonts.json`).then(r => { if (!r.ok) throw Error('Missing fonts'); return r.json(); }),
    fetch('./reference/icml2026-narrow.json').then(r => r.json()),
  ]);
  page.rules.push(...supplement.strokes.map(rule => ({...rule, y_pt: rule.y_pt - rule.height_pt / 2})));
  const style = document.createElement('style'); style.textContent = fontFaceCss(fonts, base); document.head.append(style);
  const paper = renderFixedPaper(page); document.getElementById('stage').append(paper);
  await alignFixedBaselines(paper);
  // Expose fresh measurements rather than cached expected values for regression.
  window.__fixedPage = { measure: () => measureFixedPaper(paper, page), page };
  const comparison = document.getElementById('comparison'), mode = document.getElementById('mode');
  function update() {
    comparison.dataset.mode = mode.value;
    document.getElementById('opacity-control').hidden = mode.value !== 'overlay';
  }
  mode.addEventListener('change', update);
  document.getElementById('blink').addEventListener('click', () => {
    mode.value = mode.value === 'baseline' ? 'browser' : 'baseline'; update();
  });
  document.getElementById('opacity').addEventListener('input', e => comparison.style.setProperty('--opacity', e.target.value));
  document.getElementById('status').textContent = `${page.runs.length} text/math runs · ready · fixed reference experiment`;
  window.__ready = true;
} catch (error) {
  document.getElementById('status').textContent = `Could not load reference: ${error.message}`;
  window.__referenceError = String(error);
}
