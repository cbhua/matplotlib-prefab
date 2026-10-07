"""Local Matplotlib renderer, serialized because pyplot is not thread-safe."""
from pathlib import Path
import json
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
_lock = threading.Lock()
_worker = None


def _load():
    global _worker
    if _worker is None:
        sys.path.insert(0, str(ROOT / 'skills/scientific-figures/scripts'))
        sys.path.insert(0, str(ROOT / 'web/src/python'))
        import worker_render
        worker_render.SKILL_ROOT = str(ROOT / 'skills/scientific-figures')
        _worker = worker_render
    return _worker


def environment():
    with _lock:
        return _load().environment()


def render(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('spec'), dict) or not isinstance(payload.get('profile'), dict):
        raise ValueError('Expected spec and profile JSON objects.')
    with _lock:
        result = json.loads(_load().render(json.dumps(payload)))
        result.pop('traceback', None)
        return result
