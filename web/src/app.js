/**
 * The style lab: three venues, two width modes, live matplotlib, one hand-off.
 *
 * The flow is deliberately narrow. A venue and a width mode choose a calibrated
 * paper page; that page fixes the figure's physical size; the panel edits a
 * style profile; the worker draws it with the repository's own Python; the SVG
 * goes into the page's measured slot. Nothing here computes a style number and
 * nothing draws — those live in Python so the browser and the command line
 * cannot disagree.
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

import { renderPaperPage, setFigure, clearFigure, fontFaceCss } from './paper-page.js';
import { buildPanel, ALL_CONTROLS, controlApplies, getPath, setPath, deletePath, effectiveValue } from './controls.js';
import { buildBundle, handoffText, copyToClipboard, downloadJson, stableStringify } from './export-config.js';

const BASE = new URL('./', import.meta.url).href.replace(/src\/$/, '');
const GENERATED = `${BASE}public/generated/`;
const DEBOUNCE_MS = 120;

const state = {
  venue: 'icml2026',
  layout: 'narrow',
  specName: 'line-multi',
  pages: new Map(),
  specs: new Map(),
  baseProfile: null,     // the repository profile, width untouched
  profile: null,         // the edited copy, width derived from the mode
  page: null,
  paper: null,
  slot: null,
  worker: null,
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
  return JSON.stringify([state.venue, state.layout, state.specName, state.profile]);
}

/** Export is only offered for a configuration that actually rendered. */
function refreshExportAvailability() {
  const fresh = state.lastGood && state.lastGood.signature === signature();
  for (const id of ['copy-handoff', 'copy-profile', 'download-bundle', 'download-profile', 'download-spec']) {
    el(id).disabled = !fresh;
  }
  el('export-state').textContent = fresh
    ? 'Ready: this configuration rendered successfully.'
    : 'Not ready: render the current configuration before exporting it.';
  el('export-state').dataset.ready = String(Boolean(fresh));
}

/* ------------------------------------------------------------------- data */

async function loadJson(path) {
  const response = await fetch(GENERATED + path);
  if (!response.ok) throw new Error(`${path} -> HTTP ${response.status}`);
  return response.json();
}

async function page(venue, layout) {
  const key = `${venue}/${layout}`;
  if (!state.pages.has(key)) {
    state.pages.set(key, await loadJson(`conferences/${venue}/${layout}/page.json`));
  }
  return state.pages.get(key);
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
  return profile;
}

function requestRender() {
  state.pendingDebounce = false;
  if (!state.ready || !state.profile) return;
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
  if (message.id !== state.requestId) return;
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
    render_ms: result.render_ms,
    wall_ms: message.wall_ms,
    width_mm: result.width_mm,
    height_mm: result.height_mm,
    resolved_profile: result.resolved_profile,
    resolved_spec: result.resolved_spec,
  };
  const size = `${result.width_mm.toFixed(2)} × ${result.height_mm.toFixed(2)} mm · `
    + `${result.render_ms.toFixed(0)} ms in matplotlib, ${message.wall_ms} ms round trip`;
  const problems = renderProblems(result.report);
  if (problems.length) {
    // A figure that drew is not a figure that is legible. These are render.py's
    // own checks, run on this very figure, and they are the difference between
    // a preview and a picture.
    setStatus('warn', `Drawn, with ${problems.length} thing${problems.length > 1 ? 's' : ''} to look at.`, size);
  } else {
    setStatus('ok', 'Drawn.', size);
  }
  showChecks(result.report, problems);
  updateReadout();
  refreshExportAvailability();
}

function renderProblems(report) {
  if (!report) return [];
  return report.checks.filter((check) => check.status === 'warn' || check.status === 'fail');
}

function showChecks(report, problems) {
  const host = el('checks');
  host.textContent = '';
  if (!report) {
    host.hidden = true;
    return;
  }
  host.hidden = false;
  for (const check of problems) {
    const item = document.createElement('li');
    item.className = `check check-${check.status}`;
    const label = document.createElement('strong');
    label.textContent = check.id;
    item.appendChild(label);
    item.appendChild(document.createTextNode(` ${check.message}`));
    host.appendChild(item);
  }
  const review = document.createElement('li');
  review.className = 'check check-open';
  review.textContent = problems.length
    ? 'These are heuristics, not verdicts — and nothing above replaces looking at the figure.'
    : 'Every automatic check is clean. That is not a visual review: look at the figure.';
  host.appendChild(review);
}

function updateReadout() {
  const page = state.page;
  const zoom = Number(el('zoom').value);
  el('readout').innerHTML = '';
  const rows = [
    ['Venue', `${page.venue.name} (${page.venue.mode})`],
    ['Width mode', `${page.layout.label} — ${page.layout.float_environment}`],
    ['Figure width', `${state.profile.canvas.width_mm.toFixed(3)} mm`],
    ['Figure height', `${(state.profile.canvas.width_mm * state.profile.canvas.aspect_ratio).toFixed(3)} mm`],
    ['Slot measured', `${page.slot.width_mm.toFixed(3)} × ${page.slot.height_mm.toFixed(3)} mm`],
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

function applyZoom() {
  const zoom = Number(el('zoom').value);
  el('paper-scale').style.transform = `scale(${zoom})`;
  const paper = el('paper-scale').firstElementChild;
  if (paper) {
    el('paper-frame').style.width = `${paper.offsetWidth * zoom}px`;
    el('paper-frame').style.height = `${paper.offsetHeight * zoom}px`;
  }
  el('zoom-value').textContent = `${Math.round(zoom * 100)}%`;
  if (state.page) updateReadout();
}

async function mountPage() {
  state.page = await page(state.venue, state.layout);
  const host = el('paper-scale');
  host.textContent = '';
  const rendered = renderPaperPage(state.page, { showSlotOutline: true });
  host.appendChild(rendered.paper);
  state.paper = rendered.paper;
  state.slot = rendered.slot;
  applyZoom();
  if (state.lastGood && state.lastGood.svg) setFigure(state.slot, state.lastGood.svg);
}

/* ------------------------------------------------------------------ export */

function exportState() {
  return {
    page: state.page,
    spec: state.lastGood ? state.lastGood.resolved_spec : state.currentSpec,
    profile: state.lastGood ? state.lastGood.resolved_profile : state.profile,
    resolvedType: resolvedTypeFrom(state.lastGood ? state.lastGood.resolved_profile : state.profile),
    environment: state.environment,
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

async function copyOrShow(text, label) {
  const result = await copyToClipboard(text);
  const fallback = el('copy-fallback');
  if (result.ok) {
    setStatus('ok', `${label} copied to the clipboard.`);
    fallback.hidden = true;
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
  const [manifest, fonts, index, lock] = await Promise.all([
    loadJson('assets-manifest.json'),
    loadJson('fonts/fonts.json'),
    loadJson('conferences/index.json'),
    fetch(`${BASE}pyodide.lock.json`).then((r) => r.json()),
  ]);

  const style = document.createElement('style');
  style.textContent = fontFaceCss(fonts, GENERATED);
  document.head.appendChild(style);

  const core = manifest.files.find((f) => f.target.endsWith('figure_core.py'));
  state.assets = {
    pyodide_version: lock.pyodide_version,
    figure_core_sha256: core ? core.sha256 : null,
    shared_sources: manifest.files.map((f) => ({ source: f.source, sha256: f.sha256 })),
  };

  buildVenueTabs(index);

  state.baseProfile = await loadJson('profiles/single-column.json');
  state.profile = structuredClone(state.baseProfile);
  state.currentSpec = await spec(state.specName);
  await mountPage();
  deriveWidth(state.profile, state.page);

  const handlers = {
    onChange(control, value) {
      setPath(state.profile, control.path, value);
      panel.sync(state.profile, state.baseProfile, state.currentSpec);
      scheduleRender();
    },
    onReset(control) {
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
  panel.sync(state.profile, state.baseProfile, state.currentSpec);
  updateReadout();
  refreshExportAvailability();

  wireControls();

  // Start the interpreter last, so the page is usable — and honestly labelled —
  // while it loads.
  setStatus('working', 'Loading the Python runtime…',
    `${lock.total_mib} MiB of Pyodide, matplotlib and numpy, served from this site`);
  el('preview').classList.add('is-stale');

  state.worker = new Worker(`${BASE}src/render-worker.js`, { type: 'module' });
  state.worker.onmessage = (event) => {
    const message = event.data;
    if (message.type === 'boot-progress') {
      setStatus('working', `Loading: ${message.detail}…`);
    } else if (message.type === 'ready') {
      state.ready = true;
      state.environment = message.stats.environment;
      el('runtime').textContent =
        `matplotlib ${message.stats.environment.matplotlib} · numpy ${message.stats.environment.numpy}`
        + ` · Python ${message.stats.environment.python} · Pyodide ${message.stats.pyodide_version}`
        + ` · started in ${(message.stats.total_ms / 1000).toFixed(1)} s`;
      el('boot-retry').hidden = true;
      requestRender();
    } else if (message.type === 'render-result') {
      onRenderResult(message);
    } else if (message.type === 'fatal') {
      state.bootError = message.error;
      setStatus('error', 'The Python runtime failed to start.',
        `${message.error.slice(0, 300)} — the preview cannot draw. Nothing else is `
        + 'substituted for it: a different plotting library would not be this figure.');
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
      syncLayoutButtons(available);
      await mountPage();
      deriveWidth(state.profile, state.page);
      updateReadout();
      scheduleRender();
    });
    host.appendChild(button);
  }
}

function wireControls() {
  el('zoom').addEventListener('input', applyZoom);

  el('example').addEventListener('change', async (event) => {
    state.specName = event.target.value;
    state.currentSpec = await spec(state.specName);
    state.panel.sync(state.profile, state.baseProfile, state.currentSpec);
    scheduleRender();
  });

  el('reset-all').addEventListener('click', () => state.resetAll());

  el('spec-file').addEventListener('change', async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text());
      state.currentSpec = parsed;
      state.specName = file.name.replace(/\.json$/, '');
      el('example').value = '';
      state.panel.sync(state.profile, state.baseProfile, parsed);
      scheduleRender();
      setStatus('working', `Loaded ${file.name}. The validator will accept or reject it.`);
    } catch (error) {
      setStatus('error', `${file.name} is not valid JSON.`, String(error.message || error));
    }
  });

  el('copy-handoff').addEventListener('click', () =>
    copyOrShow(handoffText(exportState()), 'The hand-off'));
  el('copy-profile').addEventListener('click', () =>
    copyOrShow(stableStringify(exportState().profile), 'The profile'));
  el('download-bundle').addEventListener('click', () =>
    downloadJson(`${state.venue}-${state.layout}-handoff.json`, buildBundle(exportState())));
  el('download-profile').addEventListener('click', () =>
    downloadJson('profile.json', exportState().profile));
  el('download-spec').addEventListener('click', () =>
    downloadJson('spec.json', exportState().spec));

  el('boot-retry').addEventListener('click', () => {
    el('boot-retry').hidden = true;
    location.reload();
  });
}

boot().catch((error) => {
  setStatus('error', 'The tool could not start.', String(error && error.stack ? error.stack : error));
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
    !state.pendingDebounce && !state.inflight && state.lastGood
    && state.lastGood.signature === signature(),
  ),
  exportBundle: () => buildBundle(exportState()),
  exportText: () => handoffText(exportState()),
  async select(venue, layout) {
    await selectVenue(venue);
    if (layout && layout !== state.layout) {
      const available = state.venueIndex.pages.filter((p) => p.venue === venue);
      state.layout = layout;
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
    setPath(state.profile, path, value);
    state.panel.sync(state.profile, state.baseProfile, state.currentSpec);
    scheduleRender();
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
