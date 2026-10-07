import { fontFaceCss } from './figure-view.js';
import { contentBlocks, paginatePaper } from './reflow-paper.js';
const el = id => document.getElementById(id);
const json = async url => { const r = await fetch(url); if (!r.ok) throw Error(`Could not load ${url}`); return r.json(); };
try {
  const [source, fonts, supplement, content] = await Promise.all([
    json('./public/generated/conferences/icml2026/narrow/page.json'), json('./public/generated/fonts/fonts.json'),
    json('./reference/icml2026-narrow.json'), json('./reference/reflow-content.json'),
  ]);
  source.rules.push(...supplement.strokes.map(r => ({...r, y_pt: r.y_pt - r.height_pt / 2})));
  const style = document.createElement('style'); style.textContent = fontFaceCss(fonts, './public/generated/'); document.head.append(style);
  let imageUrl = null, editedReferences = false, scheduled = false, running = false, revision = 0;
  function defaults() {
    el('body').value = content.body; el('caption').value = content.caption;
    el('references').value = content.references.map(r => r.segments.map(s => s.text).join('')).join('\n\n');
    el('height').value = source.slot.height_mm; el('height-slider').value = source.slot.height_mm;
    el('width').value = 'narrow'; editedReferences = false;
  }
  async function render() {
    scheduled = false;
    if (running) { schedule(); return; }
    if (!el('height').value || !el('height').checkValidity()) {
      el('error').hidden = false; el('error').textContent = 'Enter a figure height between 10 and 180 mm.'; window.__reflow.busy = false; return;
    }
    running = true; window.__reflow.busy = true;
    const started = performance.now();
    try {
      const references = editedReferences ? el('references').value.split(/\n\s*\n/).filter(s => s.trim()).map(text => ({segments: [{text: text.trim()}]})) : content.references;
      const blocks = contentBlocks(el('body').value, references);
      const result = await paginatePaper(el('pages'), source, blocks, {heightMm: Number(el('height').value),
        wide: el('width').value === 'wide', caption: el('caption').value, imageUrl});
      window.__reflow.result = {...result, durationMs: performance.now() - started, revision: ++revision};
      window.__reflow.blocks = blocks;
      el('status').textContent = `${result.pages} page${result.pages === 1 ? '' : 's'} · ${result.widthMm.toFixed(2)} × ${result.heightMm.toFixed(2)} mm`;
      el('error').hidden = true;
    } catch (error) { el('error').hidden = false; el('error').textContent = `${error.message} Previous valid layout is retained.`; }
    finally { running = false; window.__reflow.busy = scheduled; }
  }
  function schedule() { window.__reflow.busy = true; if (!scheduled) { scheduled = true; requestAnimationFrame(render); } }
  window.__reflow = {busy: true, result: null};
  el('height-slider').addEventListener('input', () => { el('height').value = el('height-slider').value; schedule(); });
  el('height').addEventListener('input', () => { el('height-slider').value = el('height').value; schedule(); });
  for (const id of ['width', 'caption', 'body']) el(id).addEventListener('input', schedule);
  el('references').addEventListener('input', () => { editedReferences = true; schedule(); });
  el('reset').addEventListener('click', () => { defaults(); if (imageUrl) URL.revokeObjectURL(imageUrl); imageUrl = null; el('image').value = ''; schedule(); });
  el('image').addEventListener('change', async () => {
    const file = el('image').files[0]; if (!file) return;
    const url = URL.createObjectURL(file), probe = new Image(); probe.src = url;
    try { await probe.decode(); if (imageUrl) URL.revokeObjectURL(imageUrl); imageUrl = url; schedule(); }
    catch { URL.revokeObjectURL(url); el('error').hidden = false; el('error').textContent = 'This file could not be decoded as an image.'; }
  });
  el('remove-image').addEventListener('click', () => { if (imageUrl) URL.revokeObjectURL(imageUrl); imageUrl = null; el('image').value = ''; schedule(); });
  defaults(); await render(); window.__ready = true;
} catch (error) { el('error').hidden = false; el('error').textContent = String(error); window.__reflowError = String(error); }
