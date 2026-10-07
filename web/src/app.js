import { initLanguage } from './i18n.js';
initLanguage();
/**
 * The style lab: native paper layout, browser SVG outlines, one hand-off.
 * The profile controls physical sizes; offline Matplotlib glyphs preserve text
 * shapes while JavaScript handles chart layout and dynamic configuration.
 *
 * Two rules that the code exists to enforce:
 *
 *   1. Never show a stale figure beside live numbers. Every render carries a
 *      request id; a reply for an id that is no longer current is dropped, and
 *      the preview is visibly marked while a render is in flight.
 *   2. Never claim a configuration was verified when it was not. The export
 *      buttons are disabled until a render has actually succeeded for the
 *      configuration currently on screen.
 */

import {validateFigureSpec} from './spec-validation.js';
import {evaluatePaper,combinedReport} from './paper-checks.js';
import { outlineRenderer } from './outline-renderer.js';
import { contentBlocks, paginatePaper } from './reflow-paper.js';
import { createSetup } from './setup.js';
import { createPage, templateIndex, validatePresets } from './css-paper.js';
import { setFigure, fontFaceCss } from './figure-view.js';
import { buildPanel, ALL_CONTROLS, controlApplies, getPath, setPath, deletePath, effectiveValue } from './controls.js';
import { buildBundle, handoffText, copyToClipboard } from './export-config.js';

const BASE = new URL('./', import.meta.url).href.replace(/src\/$/, '');
const GENERATED = `${BASE}public/generated/`;
const DEBOUNCE_MS = 120;

const state = {
  configured: false,
  config: null,
  activePanel: 0,
  venue: 'icml2026',
  layout: 'narrow',
  specName: 'line-multi',
  catalog: null,
  paperOverrides: new Map(),
  specs: new Map(),
  baseProfile: null,     // the repository profile, width untouched
  profile: null,         // the edited copy, width derived from the mode
  page: null,
  paper: null,
  slot: null,
  worker: null,
  panelSources: [],
  assets: null,
  environment: null,
  requestId: 0,
  inflight: null,
  lastGood: null,        // { signature, svg, drawn, render_ms }
  ready: false,
  bootError: null,
};

const el = (id) => document.getElementById(id);

/* ------------------------------------------------------------------ status */

function setStatus(kind, message, detail) {
  const node = el('status');
  node.dataset.kind = kind;
  node.querySelector('.status-message').textContent = message;
  node.querySelector('.status-detail').textContent = detail || '';
  node.querySelector('.status-detail').hidden = !detail;
}

function signature() {
  return JSON.stringify([state.venue, state.layout, state.currentSpec, state.profile]);
}

/** Export is only offered for a configuration that actually rendered. */
function refreshExportAvailability() {
  const fresh = !state.pendingDebounce && !state.inflight && !state.paperBusy && !state.paperError && state.lastGood && state.lastGood.signature === signature();
  for (const id of ['copy-handoff']) {
    el(id).disabled = !fresh;
  }
  el('export-state').textContent = fresh
    ? 'Ready: this configuration rendered successfully.'
    : 'Not ready: render the current configuration before exporting it.';
  el('export-state').dataset.ready = String(Boolean(fresh));
  const assessment=el('figure-assessment');
  assessment.disabled=!fresh;
  if(fresh)showChecks(state.lastGood.report,renderProblems(state.lastGood.report));
  if(!fresh){assessment.textContent=state.paperError || el('status').dataset.kind==='error'?'⚠️ Fix figure settings.':'Checking figure…';el('warning-rail').hidden=true;}

}

/* ------------------------------------------------------------------- data */

async function loadJson(path) {
  const response = await fetch(GENERATED + path);
  if (!response.ok) throw new Error(`${path} -> HTTP ${response.status}`);
  return response.json();
}

async function page(venue, layout) {
  const preset = state.catalog.presets.find(p => p.id === venue);
  if (!preset) throw new Error(`Unknown paper template: ${venue}`);
  return createPage(preset, layout, state.paperOverrides.get(`${venue}/${layout}`));
}

async function spec(name) {
  if (!state.specs.has(name)) state.specs.set(name, await loadJson(`specs/${name}.json`));
  return structuredClone(state.specs.get(name));
}

/* --------------------------------------------------------------- rendering */

function deriveWidth(profile, page) {
  // The only thing a venue/mode switch changes about the style: the canvas
  // width, taken from the slot the template measured. Every setting the user
  // has touched is kept.
  profile.canvas.width_mm = page.figure.width_mm;
  profile.canvas.aspect_ratio = page.figure.height_mm / page.figure.width_mm;
  return profile;
}

function requestRender() {
  state.pendingDebounce = false;
  if (!state.configured || !state.ready || !state.profile) return;
  const id = ++state.requestId;
  state.inflight = { id, signature: signature() };
  el('preview').classList.add('is-rendering');
  setStatus('working', 'Rendering…');
  state.worker.postMessage({
    type: 'render', id, spec: state.currentSpec, profile: state.profile,
  });
}

let debounceTimer = null;
function scheduleRender() {
  clearTimeout(debounceTimer);
  ++state.requestId; // invalidate replies even before the next debounced render starts
  state.pendingDebounce = true;
  debounceTimer = setTimeout(() => { state.pendingDebounce = false; requestRender(); }, DEBOUNCE_MS);
  // The check list belongs to the figure on screen; the moment that figure is
  // out of date, so is it.
  el('checks').hidden = true;
  // The preview is out of date the moment a control moves, and saying so
  // immediately is the point: the numbers on the right have already changed.
  el('preview').classList.add('is-stale');
  refreshExportAvailability();
}

function onRenderResult(message) {
  // A reply for a superseded request is dropped rather than drawn. Without this
  // a slow render could land after a fast one and put the wrong picture on the
  // screen next to the right numbers.
  if (message.id !== state.requestId || !state.inflight
      || state.inflight.signature !== signature()) return;
  state.inflight = null;
  el('preview').classList.remove('is-rendering');

  const result = message.result;
  if (!result.ok) {
    setStatus('error', 'This configuration could not be drawn.', result.error);
    el('preview').classList.add('is-stale');
    refreshExportAvailability();
    return;
  }

  setFigure(state.slot, result.svg);
  el('preview').classList.remove('is-stale');
  state.lastGood = {
    signature: signature(),
    svg: result.svg,
    drawn: result.drawn,
    report: result.report,
    figureReport: result.report,
    render_ms: result.render_ms,
    wall_ms: message.wall_ms,
    width_mm: result.width_mm,
    height_mm: result.height_mm,
    resolved_profile: result.resolved_profile,
    resolved_spec: result.resolved_spec,
  };
  const size = `${result.width_mm.toFixed(2)} × ${result.height_mm.toFixed(2)} mm · `
    + `${result.render_ms.toFixed(1)} ms in browser · Matplotlib outlines`;
  updatePaperAssessment();
  const problems = renderProblems(state.lastGood.report);
  if (problems.length) {
    // Browser figure checks and paper-context checks describe this preview.
    // The Python renderer performs its own independent inspection.
    setStatus('warn', `Drawn, with ${problems.length} thing${problems.length > 1 ? 's' : ''} to look at.`, size);
  } else {
    setStatus('ok', 'Drawn.', size);
  }
  showChecks(state.lastGood.report, problems);
  updateReadout();
  refreshExportAvailability();
}

function renderProblems(report) {
  if (!report) return [];
  return report.checks.filter((check) => check.status === 'warn' || check.status === 'fail');
}

function showChecks(report, problems) {
  clearIssueHighlight();
  const host=el('checks');host.replaceChildren();host.hidden=false;
  const button=el('figure-assessment');
  button.textContent=problems.length?`⚠️ There ${problems.length===1?'is 1 warning':`are ${problems.length} warnings`}.`:'✅ Nice figure!';
  button.dataset.state=problems.length?'warn':'ok';
  button.title=problems.length?'Current figure warnings':'No warnings from the current checks';
  for(const check of problems){
    const item=document.createElement('li');item.className='warning-card';item.tabIndex=0;
    item.addEventListener('mouseenter',()=>highlightIssue(check));item.addEventListener('mouseleave',clearIssueHighlight);
    item.addEventListener('focusin',()=>highlightIssue(check));item.addEventListener('focusout',clearIssueHighlight);
    const title=document.createElement('strong');title.textContent=`⚠️ ${check.title || 'Figure warning'}`;
    const detail=document.createElement('p');detail.textContent=check.message;
    item.append(title,detail);
    if(check.control){const action=document.createElement('button');action.type='button';action.className='warning-action';action.textContent='Adjust setting';action.onclick=()=>focusSetting(check.control);item.append(action);}
    host.append(item);
  }
  button.setAttribute('aria-expanded',String(Boolean(problems.length)));
  el('warning-rail').hidden=!problems.length;
}

function clearIssueHighlight(){
  document.querySelectorAll('[data-issue-overlay]').forEach(n=>n.remove());
  document.querySelectorAll('.issue-figure').forEach(n=>n.classList.remove('issue-figure'));
}
function highlightIssue(check){
  clearIssueHighlight();
  const root=state.slot?.querySelector('svg');if(!root)return;
  const panel=root.querySelectorAll('.figure-panel')[check.panel_index];
  if(panel && check.region){
    const ns='http://www.w3.org/2000/svg',overlay=document.createElementNS(ns,'g'),rect=document.createElementNS(ns,'rect');overlay.setAttribute('data-issue-overlay','');
    for(const [key,value] of Object.entries({...check.region,fill:'#b66a1215',stroke:'#a86b24','stroke-width':1.5,'stroke-dasharray':'5 4','vector-effect':'non-scaling-stroke'}))rect.setAttribute(key,value);
    overlay.append(rect);panel.append(overlay);return;
  }
  const nodes=panel && check.subjects?.length?[...panel.querySelectorAll('[data-chart-text]')].filter(n=>check.subjects.includes(n.dataset.chartText)):[];
  if(!nodes.length){state.paper.querySelector('.reflow-figure')?.classList.add('issue-figure');return;}
  const ns='http://www.w3.org/2000/svg',overlay=document.createElementNS(ns,'g');overlay.setAttribute('data-issue-overlay','');overlay.setAttribute('aria-hidden','true');
  const inverse=root.getScreenCTM().inverse();
  for(const node of nodes){const box=node.getBoundingClientRect(),a=new DOMPoint(box.left,box.top).matrixTransform(inverse),b=new DOMPoint(box.right,box.bottom).matrixTransform(inverse);const rect=document.createElementNS(ns,'rect');
    for(const [key,value] of Object.entries({x:a.x-1,y:a.y-1,width:b.x-a.x+2,height:b.y-a.y+2,fill:'#b66a1215',stroke:'#a86b24','stroke-width':1.5,'vector-effect':'non-scaling-stroke'}))rect.setAttribute(key,value);overlay.append(rect);}
  root.append(overlay);
}
function focusSetting(path) {
  const control=path.startsWith('figure-')?el(path):document.querySelector(`[data-path="${path}"] input:not([type=hidden])`);
  if(!control)return;
  control.closest('details')?.setAttribute('open','');
  control.scrollIntoView({block:'center',behavior:'smooth'});control.focus({preventScroll:true});
  const row=control.closest('.control')||control.closest('.paper-setting');row?.classList.add('setting-highlight');
  setTimeout(()=>row?.classList.remove('setting-highlight'),1600);
}
function updateReadout() {
  const page = state.page;
  const zoom = Number(el('zoom').value);
  el('configuration-summary').textContent = `${page.venue.name} · ${state.config?.rows || 1} × ${state.config?.columns || 1} · ${page.layout.label}`;
  el('readout').innerHTML = '';
  const rows = [
    ['Venue', page.venue.name],
    ['Page preview', 'HTML/CSS · proportional reference'],
    ['Width mode', page.layout.label],
    ['Panel layout', `${state.config?.rows || 1} × ${state.config?.columns || 1} (rows × columns)`],
    ['Figure width', `${state.profile.canvas.width_mm.toFixed(3)} mm`],
    ['Figure height', `${(state.profile.canvas.width_mm * state.profile.canvas.aspect_ratio).toFixed(3)} mm`],
    ['Figure slot', `${page.slot.width_mm.toFixed(3)} × ${page.slot.height_mm.toFixed(3)} mm`],
    ['Body type', `${page.template.body_font_size_pt} pt`],
    ['Caption type', `${page.template.caption_font_size_pt} pt`],
    ['Preview zoom', `${Math.round(zoom * 100)}% — a screen size, not a printed one`],
  ];
  for (const [name, value] of rows) {
    const row = document.createElement('div');
    row.className = 'readout-row';
    row.innerHTML = `<dt></dt><dd></dd>`;
    row.querySelector('dt').textContent = name;
    row.querySelector('dd').textContent = value;
    el('readout').appendChild(row);
  }
}

/* ------------------------------------------------------------------- paper */

let autoZoom = true;
function applyZoom() {
  const paper = el('paper-scale').firstElementChild;
  if (autoZoom && paper && !el('editor').hidden) {
    const availableWidth = el('preview').clientWidth - 16;
    const fit = Math.min(availableWidth / paper.offsetWidth, 1.6);
    el('zoom').value = Math.max(.1, fit);
  }
  const zoom = Number(el('zoom').value);
  el('paper-scale').style.transform = `scale(${zoom})`;
  if (paper) {
    el('paper-frame').style.width = `${paper.offsetWidth * zoom}px`;
    el('paper-frame').style.height = `${el('paper-scale').scrollHeight * zoom}px`;
  }
  el('zoom-value').textContent = `${Math.round(zoom * 100)}%`;
  if (state.page) updateReadout();
}

async function mountPage() {
  state.page = await page(state.venue, state.layout);
  el('wrap-note').hidden = !state.page.layout.text_wrap;
  syncPaperControls();
  await fitPaper();
  applyZoom();
}

/* ------------------------------------------------------------------ export */

function exportState() {
  return {
    page: state.page,
    panelSources: state.panelSources,
    spec: state.lastGood ? state.lastGood.resolved_spec : state.currentSpec,
    profile: state.lastGood ? state.lastGood.resolved_profile : state.profile,
    resolvedType: resolvedTypeFrom(state.lastGood ? state.lastGood.resolved_profile : state.profile),
    environment: { ...state.environment },
    assets: state.assets,
    render: state.lastGood ? {
      drawn: state.lastGood.drawn,
      width_mm: state.lastGood.width_mm,
      height_mm: state.lastGood.height_mm,
      render_ms: state.lastGood.render_ms,
      checks: state.lastGood.report,
    } : null,
  };
}

/**
 * Mirrors figure_core.resolved_type. It is duplicated here only for display and
 * for the hand-off text; the drawing never reads it, and the exported profile
 * is the Python-validated one, so the two cannot silently diverge in the output
 * that matters.
 */
const SIZE_FALLBACKS = {
  x_label: ['fonts.size_x_label_pt', 'fonts.size_axis_label_pt'],
  y_label: ['fonts.size_y_label_pt', 'fonts.size_axis_label_pt'],
  xtick: ['fonts.size_xtick_pt', 'fonts.size_tick_pt'],
  ytick: ['fonts.size_ytick_pt', 'fonts.size_tick_pt'],
  legend: ['fonts.size_legend_pt'],
  title: ['fonts.size_title_pt'],
};
const WEIGHT_FALLBACKS = {
  x_label: ['fonts.weight_x_label', 'fonts.weight'],
  y_label: ['fonts.weight_y_label', 'fonts.weight'],
  xtick: ['fonts.weight_xtick', 'fonts.weight'],
  ytick: ['fonts.weight_ytick', 'fonts.weight'],
  legend: ['fonts.weight_legend', 'fonts.weight'],
  title: ['fonts.weight_title', 'fonts.weight'],
};

function firstDefined(profile, paths) {
  for (const path of paths) {
    const value = getPath(profile, path);
    if (value !== undefined && value !== null) return value;
  }
  return undefined;
}

function resolvedTypeFrom(profile) {
  const out = {};
  for (const role of Object.keys(SIZE_FALLBACKS)) {
    out[role] = {
      size_pt: firstDefined(profile, SIZE_FALLBACKS[role]),
      weight: firstDefined(profile, WEIGHT_FALLBACKS[role]) ?? 'normal',
    };
  }
  return out;
}

let copyFeedbackTimer;
async function copyOrShow(text, label) {
  const result = await copyToClipboard(text);
  const fallback = el('copy-fallback');
  if (result.ok) {
    setStatus('ok', `${label} copied to the clipboard.`);
    fallback.hidden = true;
    const button=el('copy-handoff');button.textContent='Copied!';
    clearTimeout(copyFeedbackTimer);copyFeedbackTimer=setTimeout(()=>button.textContent='🤖 Copy for Agents',1600);
    el('copy-feedback').textContent='Figure instructions copied to clipboard.';
    return;
  }
  // Not an error to hide: show the text so it can be selected by hand, and say
  // why the clipboard refused.
  fallback.hidden = false;
  fallback.querySelector('textarea').value = text;
  fallback.querySelector('.copy-fallback-reason').textContent =
    `The browser refused clipboard access (${result.error}). Select the text below instead.`;
  fallback.querySelector('textarea').focus();
  fallback.querySelector('textarea').select();
  setStatus('warn', `${label} is ready below — the clipboard was not available.`);
}

/* -------------------------------------------------------------------- boot */

async function boot() {
  const [manifest, fonts, catalog, lock, prose] = await Promise.all([
    loadJson('assets-manifest.json'),
    loadJson('fonts/fonts.json'),
    fetch(`${BASE}presets/papers.json`).then(r => { if (!r.ok) throw new Error('Paper presets could not load'); return r.json(); }),
    fetch(`${BASE}pyodide.lock.json`).then((r) => r.json()),
    fetch(`${BASE}reference/reflow-content.json`).then(r => r.json()),
  ]);

  const style = document.createElement('style');
  style.textContent = fontFaceCss(fonts, GENERATED);
  document.head.appendChild(style);

  const core = manifest.files.find((f) => f.target.endsWith('figure_core.py'));
  state.assets = {
    paper_engine: 'native HTML/CSS',
    paper_presets: 'presets/papers.json',
    pyodide_version: lock.pyodide_version,
    figure_core_sha256: core ? core.sha256 : null,
    shared_sources: manifest.files.map((f) => ({ source: f.source, sha256: f.sha256 })),
  };

  state.catalog = validatePresets(catalog);
  state.prose = prose;
  const index = templateIndex(state.catalog);
  buildVenueTabs(index);

  state.baseProfile = await loadJson('profiles/single-column.json');
  state.bootstrap = { manifest, lock };
  state.setup = createSetup(el('setup'), index, startEditor, () => {
    el('setup').hidden = true;
    el('editor').hidden = false;
  });
}

async function startEditor(config) {
  const previous = state.currentSpec?.kind === 'grid' ? state.currentSpec.panels
    : state.currentSpec ? [state.currentSpec] : [];
  const oldConfig = state.config;
  const panels = await Promise.all(config.kinds.map(async (kind, i) => {
    const row = Math.floor(i / config.columns), column = i % config.columns;
    const oldIndex = oldConfig && column < oldConfig.columns ? row * oldConfig.columns + column : -1;
    const old = previous[oldIndex];
    return old?.kind === kind ? structuredClone(old) : spec(kind === 'line' ? 'line-multi' : kind==='scatter'?'scatter':'bar-signed');
  }));
  state.panelSources=config.kinds.map((kind,i)=>{const row=Math.floor(i/config.columns),column=i%config.columns;const oldIndex=oldConfig&&column<oldConfig.columns?row*oldConfig.columns+column:-1;return previous[oldIndex]?.kind===kind && state.panelSources[oldIndex]?state.panelSources[oldIndex]:{kind:'example',id:kind==='line'?'line-multi':kind==='scatter'?'scatter':'bar-signed'};});
  state.config = structuredClone(config);
  state.venue = config.venue;
  state.layout = config.layout;
  state.currentSpec = panels.length === 1 ? panels[0] : {
    schema_version: '1', kind: 'grid', rows: config.rows, columns: config.columns, panels,
  };
  state.activePanel = 0;
  state.profile ||= structuredClone(state.baseProfile);
  state.lastGood = null;
  ++state.requestId;
  await mountPage();
  deriveWidth(state.profile, state.page);
  state.configured = true;
  el('setup').hidden = true;
  el('editor').hidden = false;
  applyZoom();
  syncPanelPicker();
  fitPaper();
  for (const tab of el('venue-tabs').children) {
    const selected = tab.id === `tab-${state.venue}`;
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
  }
  const { manifest, lock } = state.bootstrap;

  const history=[];let lastEdit=null;
  const remember=key=>{
    const now=performance.now();
    if(!lastEdit || lastEdit.key!==key || now-lastEdit.time>700){history.push(structuredClone(state.profile));if(history.length>30)history.shift();}
    lastEdit={key,time:now};el('undo-style').disabled=!history.length;
  };
  state.undoStyle=()=>{if(!history.length)return;state.profile=history.pop();deriveWidth(state.profile,state.page);lastEdit=null;panel.sync(state.profile,state.baseProfile,state.currentSpec);el('undo-style').disabled=!history.length;scheduleRender();};
  const handlers = {
    onChange(control, value) {
      remember(control.path);
      setPath(state.profile, control.path, value);
      panel.sync(state.profile, state.baseProfile, state.currentSpec);
      scheduleRender();
    },
    onReset(control) {
      remember('reset-'+(control?.path||'all'));
      if (control) {
        // Resetting an override *removes* it rather than writing the fallback's
        // number in: the field then follows the shared value again, which is
        // what "default" means here.
        if (control.fallback) deletePath(state.profile, control.path);
        else setPath(state.profile, control.path, getPath(state.baseProfile, control.path));
      } else {
        state.profile = structuredClone(state.baseProfile);
        deriveWidth(state.profile, state.page);
      }
      panel.sync(state.profile, state.baseProfile, state.currentSpec);
      scheduleRender();
    },
  };
  const panel = buildPanel(el('panel'), handlers);
  state.panel = panel;
  state.resetAll = () => handlers.onReset(null);
  state.setStyleControl=handlers.onChange;
  panel.sync(state.profile, state.baseProfile, state.currentSpec);
  updateReadout();
  refreshExportAvailability();

  if (!state.controlsWired) { wireControls(); state.controlsWired = true; }
  if (state.worker) {
    if (state.ready) requestRender();
    return;
  }

  // Load outline assets after setup has a complete configuration.
  setStatus('working', 'Connecting to the figure renderer…');
  el('preview').classList.add('is-stale');

  state.worker = outlineRenderer(BASE);
  state.worker.onmessage = (event) => {
    const message = event.data;
    if (message.type === 'boot-progress') {
      setStatus('working', `Loading: ${message.detail}…`);
    } else if (message.type === 'ready') {
      state.ready = true;
      state.environment = message.stats.environment;
      state.assets.render_backend = message.stats.backend || 'pyodide';
      if (message.stats.backend) state.assets.pyodide_version = null;
      el('runtime').textContent = 'SVG outlines · browser renderer v0.5.0 · no Python runtime';
      el('boot-retry').hidden = true;
      requestRender();
    } else if (message.type === 'render-result') {
      onRenderResult(message);
    } else if (message.type === 'fatal') {
      state.bootError = message.error;
      setStatus('error', 'The outline renderer failed to start.',
        `${message.error.slice(0, 300)} — check that the static outline assets are available.`);
      el('boot-retry').hidden = false;
    }
  };
  state.worker.postMessage({
    type: 'boot',
    config: { pyodideDir: `${GENERATED}pyodide/`, generatedDir: GENERATED, manifest },
  });
}

function buildVenueTabs(index) {
  const tabs = el('venue-tabs');
  tabs.textContent = '';
  const venues = [];
  for (const entry of index.pages) {
    if (!venues.some((v) => v.id === entry.venue)) {
      venues.push({ id: entry.venue, name: entry.name });
    }
  }
  venues.forEach((venue, position) => {
    const tab = document.createElement('button');
    tab.type = 'button';
    tab.role = 'tab';
    tab.id = `tab-${venue.id}`;
    tab.className = 'tab';
    tab.textContent = venue.name;
    tab.setAttribute('aria-selected', String(venue.id === state.venue));
    tab.tabIndex = venue.id === state.venue ? 0 : -1;
    tab.addEventListener('click', () => selectVenue(venue.id));
    tab.addEventListener('keydown', (event) => {
      const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
      if (!step) return;
      event.preventDefault();
      const next = venues[(position + step + venues.length) % venues.length];
      selectVenue(next.id);
      document.getElementById(`tab-${next.id}`).focus();
    });
    tabs.appendChild(tab);
  });
  state.venueIndex = index;
}

async function selectVenue(venueId) {
  state.venue = venueId;
  if (state.config) state.config.venue = venueId;
  for (const tab of el('venue-tabs').children) {
    const selected = tab.id === `tab-${venueId}`;
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
  }
  const available = state.venueIndex.pages.filter((p) => p.venue === venueId);
  if (!available.some((p) => p.layout === state.layout)) state.layout = available[0].layout;
  syncLayoutButtons(available);
  await mountPage();
  // Switching venue re-derives the width and keeps every style edit. That is
  // the point of the mode switch: you are asking what these settings look like
  // over there, not starting again.
  deriveWidth(state.profile, state.page);
  state.panel.sync(state.profile, state.baseProfile, state.currentSpec);
  updateReadout();
  scheduleRender();
}

function syncLayoutButtons(available) {
  const host = el('layout-buttons');
  host.textContent = '';
  for (const entry of available) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'chip';
    button.textContent = entry.label;
    button.title = `${entry.float_environment} · ${entry.figure_width_mm.toFixed(2)} mm`;
    button.setAttribute('aria-pressed', String(entry.layout === state.layout));
    button.addEventListener('click', async () => {
      state.layout = entry.layout;
      if (state.config) state.config.layout = entry.layout;
      syncLayoutButtons(available);
      await mountPage();
      deriveWidth(state.profile, state.page);
      updateReadout();
      scheduleRender();
    });
    host.appendChild(button);
  }
}

function replaceActiveSpec(value,source,index=state.activePanel) {
  state.panelSources[index]=source;
  if (state.currentSpec.kind === 'grid') state.currentSpec.panels[index] = value;
  else state.currentSpec = value;
  state.config.kinds[index] = value.kind;
  syncPanelPicker();
}

function syncPanelPicker() {
  const panels = state.currentSpec.kind === 'grid' ? state.currentSpec.panels : [state.currentSpec];
  el('panel-picker-group').hidden = panels.length === 1;
  el('active-panel').replaceChildren();
  panels.forEach((panel, i) => {
    const option = document.createElement('option');
    option.value = i;
    option.textContent = `Panel ${i + 1} · ${panel.kind}`;
    el('active-panel').append(option);
  });
  el('active-panel').value = state.activePanel;
  el('example').value = state.panelSources[state.activePanel]?.id || '';
  el('spec-file').value = '';
  syncDataOrigin();
}

function syncDataOrigin(){const source=state.panelSources[state.activePanel];const label=el('data-origin');label.textContent=source?.kind==='user-import'?'Imported data':'Example data';label.title=source?.kind==='user-import'?source.name:'Illustrative values for choosing scale and style.';}
function updatePaperAssessment(){
  if(state.paper && state.lastGood?.signature===signature())state.lastGood.report=combinedReport(state.lastGood.figureReport,evaluatePaper(state.page,state.profile,state.currentSpec,state.paper));
}
let paperRevision = 0;
async function fitPaper() {
  if (!state.page || !state.prose) return;
  const revision = ++paperRevision;
  state.paperBusy = true;
  refreshExportAvailability();
  const svg = state.slot?.querySelector('svg');
  try {
    const source = state.page;
    source.article = structuredClone(state.prose);
    const blocks = contentBlocks(state.prose.body, state.prose.references);
    const result = await paginatePaper(el('paper-scale'), source, blocks, {
      heightMm: source.figure.height_mm, wide: state.layout === 'wide' || source.figure.width_mm > source.text_block.column_width_mm, caption: state.prose.caption,
      showDimensions: false, maxPages: 1, shouldCommit: () => revision === paperRevision,
    });
    if (!result) return;
    state.paper = el('paper-scale').firstElementChild;
    state.slot = state.paper.querySelector('.reflow-slot');
    if(state.lastGood?.signature===signature())setFigure(state.slot,state.lastGood.svg);
    else if (svg) state.slot.append(svg);
    else if (state.lastGood?.svg) setFigure(state.slot, state.lastGood.svg);
    state.paperError = null;
    state.pageCount = result.pages;
    state.paper.dataset.overflow = 'false';
    el('paper-overflow').hidden = true;

    applyZoom();
    updatePaperAssessment();
  } catch (error) {
    if (revision !== paperRevision) return;
    state.paperError = error.message;
    el('paper-overflow').hidden = false;
    el('paper-overflow').textContent = `${error.message} Previous valid paper layout is retained.`;
  } finally { if (revision === paperRevision) { state.paperBusy = false; refreshExportAvailability(); } }
}

async function changeFigureDimension(axis, value) {
  const max=axis==='width'?state.page.text_block.width_mm:180;
  if (!Number.isFinite(value) || value < (axis==='width'?30:10) || value > max) return;
  const key = `${state.venue}/${state.layout}`;
  state.paperOverrides.set(key, {figure_width_mm:state.page.figure.width_mm,figure_height_mm:state.page.figure.height_mm,...state.paperOverrides.get(key), [`figure_${axis}_mm`]: value});
  state.page = await page(state.venue, state.layout);
  deriveWidth(state.profile, state.page);
  syncPaperControls(); fitPaper(); updateReadout(); scheduleRender();
}
function syncPaperControls() {
  for(const axis of ['width','height']) {
    const max=axis==='width'?state.page.text_block.width_mm:180;
    for(const suffix of ['', '-slider']){const input=el(`figure-${axis}${suffix}`);input.max=max;input.value=state.page.figure[`${axis}_mm`].toFixed(2);}
  }
}
let exampleRevision = 0;
function wireControls() {
  for(const axis of ['width','height'])for(const suffix of ['', '-slider'])el(`figure-${axis}${suffix}`).addEventListener('input',event=>{
    if(event.target.value && event.target.checkValidity())changeFigureDimension(axis,Number(event.target.value));
  });
  el('active-panel').addEventListener('change', event => {
    state.activePanel = Number(event.target.value);
    el('example').value = state.panelSources[state.activePanel]?.id || '';
    el('spec-file').value = '';
    syncDataOrigin();
  });
  el('figure-assessment').addEventListener('click',()=>el('checks').querySelector('.warning-card')?.focus());
  el('zoom').addEventListener('input', () => { autoZoom = false; applyZoom(); });
  window.addEventListener('resize', applyZoom);

  el('example').addEventListener('change', async (event) => {
    const name=event.target.value;
    const panelIndex=state.activePanel;
    const revision=++exampleRevision;
    state.pendingDebounce=true;refreshExportAvailability();
    try {
      state.specName=name;
      const next=await spec(name);
      if(revision!==exampleRevision)return;
      replaceActiveSpec(next,{kind:'example',id:name},panelIndex);
      state.panel.sync(state.profile,state.baseProfile,state.currentSpec);
      scheduleRender();
    } catch(error) {
      if(revision!==exampleRevision)return;
      state.pendingDebounce=false;setStatus('error','Could not load this example.',error.message);refreshExportAvailability();
    }
  });

  el('reset-all').addEventListener('click', () => state.resetAll());
  el('undo-style').addEventListener('click',()=>state.undoStyle());
  el('reset-size').addEventListener('click',async()=>{
    const key=`${state.venue}/${state.layout}`;state.paperOverrides.delete(key);state.page=await page(state.venue,state.layout);
    deriveWidth(state.profile,state.page);syncPaperControls();fitPaper();updateReadout();scheduleRender();
  });

  el('spec-file').addEventListener('change', async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    const panelIndex=state.activePanel;
    const revision=++exampleRevision;state.pendingDebounce=true;refreshExportAvailability();
    try {
      const parsed = JSON.parse(await file.text());
      if(revision!==exampleRevision)return;
      validateFigureSpec(parsed,{grid:false});
      replaceActiveSpec(parsed,{kind:'user-import',name:file.name},panelIndex);
      state.specName = file.name.replace(/\.json$/, '');
      state.panel.sync(state.profile, state.baseProfile, state.currentSpec);
      scheduleRender();
      setStatus('working', `Loaded ${file.name}. The validator will accept or reject it.`);
    } catch (error) {
      if(revision!==exampleRevision)return;
      state.pendingDebounce=false;
      setStatus('error', `Could not import ${file.name}.`, String(error.message || error));
      refreshExportAvailability();
    }
  });

  el('copy-handoff').addEventListener('click', () =>
    copyOrShow(handoffText(exportState()), 'The hand-off'));
  el('boot-retry').addEventListener('click', () => {
    el('boot-retry').hidden = true;
    location.reload();
  });
}

boot().catch((error) => {
  el('setup').textContent = `The templates could not load. Reload to retry. ${error.message || error}`;
  state.bootError = String(error);
});

/*
 * The test surface.
 *
 * Browser tests need to wait for a render and read what the page believes,
 * rather than scraping its pixels and hoping. `state` is exposed for that.
 *
 * `renderOnce` talks to the same worker the UI uses but does not touch the UI,
 * which is what the equivalence check wants: it is comparing what the shared
 * Python draws in a browser with what it draws locally, and routing that through
 * sliders would only add ways for the test to be measuring the wrong thing.
 */
window.__lab = state;
window.__labApi = {
  ready: () => state.ready,
  bootError: () => state.bootError,
  renderOnce(spec, profile) {
    return new Promise((resolve) => {
      const id = 1_000_000 + Math.floor(Math.random() * 1_000_000);
      const worker = state.worker;
      const listener = (event) => {
        if (event.data.type === 'render-result' && event.data.id === id) {
          worker.removeEventListener('message', listener);
          resolve(event.data);
        }
      };
      worker.addEventListener('message', listener);
      worker.postMessage({ type: 'render', id, spec, profile });
    });
  },
  currentProfile: () => structuredClone(state.profile),
  currentSpec: () => structuredClone(state.currentSpec),
  currentPage: () => state.page,
  lastGood: () => state.lastGood,
  /**
   * Nothing is queued, nothing is in flight, and the figure on screen belongs to
   * the configuration on screen. Tests wait on this rather than on "a render
   * happened": a debounced request that has not fired yet would otherwise land
   * mid-assertion and put the page back into its working state.
   */
  idle: () => Boolean(
    !state.paperBusy && !state.pendingDebounce && !state.inflight && state.lastGood
    && state.lastGood.signature === signature(),
  ),
  exportBundle: () => buildBundle(exportState()),
  exportText: () => handoffText(exportState()),
  async select(venue, layout) {
    await selectVenue(venue);
    if (layout && layout !== state.layout) {
      const available = state.venueIndex.pages.filter((p) => p.venue === venue);
      state.layout = layout;
      if (state.config) state.config.layout = layout;
      syncLayoutButtons(available);
      await mountPage();
      deriveWidth(state.profile, state.page);
      updateReadout();
      scheduleRender();
    }
    return { venue: state.venue, layout: state.layout };
  },
  setControl(path, value) {
    const control = ALL_CONTROLS.find((entry) => entry.path === path);
    if (!control) throw new Error(`no control writes ${path}`);
    state.setStyleControl(control,value);
  },
  resetAll: () => state.resetAll(),
  controls: () => ALL_CONTROLS.map(({ path, fallback, label, kind, groupKinds, requiresTitle }) =>
    ({ path, fallback, label, kind: kind || 'number', kinds: groupKinds || null,
       requiresTitle: Boolean(requiresTitle) })),
  controlApplies: (path) => {
    const control = ALL_CONTROLS.find((entry) => entry.path === path);
    return control ? controlApplies(control, state.currentSpec) : false;
  },
  signature: () => signature(),
};
