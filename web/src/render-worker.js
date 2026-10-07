/**
 * The Python side of the tool, off the main thread.
 *
 * Pyodide takes seconds to start and a matplotlib render takes tens of
 * milliseconds; both would block the UI thread. This worker owns the
 * interpreter, and the page talks to it in messages.
 *
 * Two rules make the reply trustworthy:
 *
 *   1. One job at a time. A new request arriving while a render is running does
 *      not queue behind it — it *replaces* whatever was waiting, and the reply
 *      carries the request id, so the page can drop a result that arrived for a
 *      configuration the user has already moved past. Stale pixels shown next to
 *      live numbers is the failure mode this design exists to prevent.
 *   2. Nothing is invented here. Every number in the SVG comes from the Python
 *      in figure_core; this file never touches font sizes or geometry.
 */

let pyodide = null;
let renderFn = null;
let pending = null;      // the newest request not yet started
let running = false;
let bootPromise = null;
let bootStats = null;

const post = (message) => self.postMessage(message);

async function fetchText(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url} -> HTTP ${response.status}`);
  }
  return response.text();
}

/**
 * Load Pyodide from our own copy, install the pinned wheels, and write the
 * repository's Python into the in-memory filesystem under /skill, mirroring the
 * skill's real directory shape so figure_core finds its templates unmodified.
 */
async function boot(config) {
  const t0 = performance.now();
  const { pyodideDir, manifest } = config;

  post({ type: 'boot-progress', stage: 'runtime', detail: 'loading the Python runtime' });
  const { loadPyodide } = await import(`${pyodideDir}pyodide.mjs`);
  pyodide = await loadPyodide({ indexURL: pyodideDir });
  const tRuntime = performance.now();

  post({ type: 'boot-progress', stage: 'packages', detail: 'loading matplotlib and numpy' });
  await pyodide.loadPackage('matplotlib');
  const tPackages = performance.now();

  post({ type: 'boot-progress', stage: 'sources', detail: 'installing the repository code' });
  const fs = pyodide.FS;
  for (const dir of ['/skill', '/skill/scripts', '/skill/assets', '/skill/assets/templates']) {
    try { fs.mkdir(dir); } catch (e) { /* already there */ }
  }
  const targets = {
    'python/skill/scripts/grid_core.py': '/skill/scripts/grid_core.py',
    'python/skill/scripts/figure_core.py': '/skill/scripts/figure_core.py',
    'python/skill/scripts/inspect_figure.py': '/skill/scripts/inspect_figure.py',
    'python/skill/assets/templates/line.py': '/skill/assets/templates/line.py',
    'python/skill/assets/templates/bar.py': '/skill/assets/templates/bar.py',
    'python/worker_render.py': '/skill/scripts/worker_render.py',
  };
  const copied = [];
  for (const entry of manifest.files) {
    const destination = targets[entry.target];
    if (!destination) continue;
    const source = await fetchText(`${config.generatedDir}${entry.target}`);
    fs.writeFile(destination, source);
    copied.push({ target: entry.target, sha256: entry.sha256 });
  }

  pyodide.runPython(`
import sys
if '/skill/scripts' not in sys.path:
    sys.path.insert(0, '/skill/scripts')
`);
  const worker = pyodide.pyimport('worker_render');
  renderFn = worker.render;
  const environment = JSON.parse(pyodide.runPython(
    'import json, worker_render; json.dumps(worker_render.environment())'
  ));
  const tSources = performance.now();

  bootStats = {
    runtime_ms: Math.round(tRuntime - t0),
    packages_ms: Math.round(tPackages - tRuntime),
    sources_ms: Math.round(tSources - tPackages),
    total_ms: Math.round(tSources - t0),
    sources: copied,
    environment,
    pyodide_version: pyodide.version,
  };
  post({ type: 'ready', stats: bootStats });
  return bootStats;
}

/**
 * Run the newest pending request, then whatever replaced it while that ran.
 * Intermediate requests are dropped on purpose: the user has moved the slider
 * past them and rendering every position would only add latency.
 */
async function drain() {
  if (running) return;
  running = true;
  try {
    while (pending) {
      const job = pending;
      pending = null;
      const started = performance.now();
      let reply;
      try {
        reply = JSON.parse(renderFn(JSON.stringify({ spec: job.spec, profile: job.profile })));
      } catch (error) {
        reply = { ok: false, error: String(error && error.message ? error.message : error),
                  error_kind: 'WorkerError' };
      }
      post({
        type: 'render-result',
        id: job.id,
        superseded: pending !== null,
        wall_ms: Math.round(performance.now() - started),
        result: reply,
      });
    }
  } finally {
    running = false;
  }
}

self.onmessage = async (event) => {
  const message = event.data || {};
  try {
    if (message.type === 'boot') {
      if (!bootPromise) bootPromise = boot(message.config);
      await bootPromise;
      return;
    }
    if (message.type === 'render') {
      if (!bootPromise) {
        post({ type: 'render-result', id: message.id, result:
               { ok: false, error: 'The Python runtime has not been started yet.' } });
        return;
      }
      await bootPromise;
      pending = { id: message.id, spec: message.spec, profile: message.profile };
      drain();
      return;
    }
    if (message.type === 'ping') {
      post({ type: 'pong', ready: renderFn !== null, stats: bootStats });
      return;
    }
  } catch (error) {
    post({
      type: 'fatal',
      stage: message.type || 'unknown',
      error: String(error && error.stack ? error.stack : error),
    });
  }
};
