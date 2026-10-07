/** Worker-compatible adapter: one server request at a time, newest queued edit wins. */
export function serverRenderer(capabilities) {
  let pending = null, running = false;
  const adapter = {onmessage: null, terminate() { pending = null; adapter.onmessage = null; },
    postMessage(message) {
      if (message.type === 'boot') {
        queueMicrotask(() => emit({type: 'ready', stats: {environment: capabilities.environment,
          backend: 'matplotlib-server', total_ms: 0, pyodide_version: null}}));
      } else if (message.type === 'render') { pending = message; drain(); }
    }};
  const emit = data => adapter.onmessage?.({data});
  async function drain() {
    if (running) return;
    running = true;
    try {
      while (pending) {
        const job = pending; pending = null; const started = performance.now();
        let result;
        try {
          const response = await fetch('/api/render', {method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({spec: job.spec, profile: job.profile})});
          result = await response.json();
          if (!response.ok) result = {ok: false, error: result.error || `Renderer returned HTTP ${response.status}`};
        } catch (error) { result = {ok: false, error: `Matplotlib server unavailable: ${error.message}`}; }
        emit({type: 'render-result', id: job.id, result, wall_ms: Math.round(performance.now() - started)});
      }
    } finally { running = false; }
  }
  return adapter;
}
