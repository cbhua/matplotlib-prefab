"""A throwaway HTTP server for the browser tests, on a free port.

The browser tests need real HTTP: workers, WebAssembly and module imports are
all refused from ``file://``. This is the same handler ``web/serve.py`` uses, so
a test and a hand-run preview are served identically — a test that passed
against a different server than the one a person uses would not mean much.
"""

from __future__ import annotations

import contextlib
import os
import sys
import threading

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB_DIR = os.path.join(REPO_ROOT, "web")
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

import serve as web_serve  # noqa: E402


@contextlib.contextmanager
def static_server(root: str = REPO_ROOT, renderer: bool = False):
    """Serve ``root`` on a free loopback port for the life of the block."""
    import functools

    handler = functools.partial(web_serve.Handler, directory=os.path.abspath(root))
    web_serve.Server.verbose = False
    httpd = web_serve.Server(("127.0.0.1", 0), handler)
    httpd.renderer_enabled = renderer
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:%d" % httpd.server_address[1]
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
