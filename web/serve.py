#!/usr/bin/env python3
"""Serve the paper tool and local Matplotlib rendering API.

    python web/serve.py                 # http://127.0.0.1:8765/
    python web/serve.py --port 9000
    python web/serve.py --root .        # repository root, for the test harness

``file://`` will not work and this script does not pretend otherwise: the tool
loads a Web Worker and a WebAssembly module, and browsers refuse both from a
file URL. Any static HTTP server does; this one exists so the repository has a
command that needs nothing installed.

Static files are read-only; /api/render accepts inline figure specifications.
It binds to the loopback interface. Use --static-only to disable the renderer. It is
a preview server, not a deployment: it does no caching, no compression and no
access control.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import os
import socketserver
import sys
import json
from urllib.parse import urlparse

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ROOT = os.path.join(REPO_ROOT, "web")


class Handler(http.server.SimpleHTTPRequestHandler):
    """Static files, with the two content types Pyodide needs to be told about.

    Python's mimetypes database predates both, and a wasm module served as
    application/octet-stream fails to stream-compile while an .mjs served as
    text/plain is refused by the module loader — in both cases with an error
    that points at the page rather than at the server.
    """

    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".wasm": "application/wasm",
        ".mjs": "text/javascript",
        ".js": "text/javascript",
        ".json": "application/json",
        ".svg": "image/svg+xml",
        ".woff2": "font/woff2",
        ".woff": "font/woff",
        ".otf": "font/otf",
        ".ttf": "font/ttf",
    }

    def json_reply(self, status, payload):
        data = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if self.path == '/api/renderer' and self.server.renderer_enabled:
            try:
                import figure_backend
                return self.json_reply(200, {'backend': 'matplotlib-server', 'environment': figure_backend.environment()})
            except Exception as exc:
                return self.json_reply(503, {'error': str(exc)})
        return super().do_GET()

    def do_POST(self):
        if self.path != '/api/render' or not self.server.renderer_enabled:
            return self.json_reply(404, {'ok': False, 'error': 'Renderer endpoint unavailable.'})
        origin = self.headers.get('Origin')
        if origin and urlparse(origin).netloc != self.headers.get('Host'):
            return self.json_reply(403, {'ok': False, 'error': 'Use the renderer from the same origin.'})
        if self.headers.get_content_type() != 'application/json':
            return self.json_reply(415, {'ok': False, 'error': 'Expected application/json.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 2 * 1024 * 1024:
                return self.json_reply(413, {'ok': False, 'error': 'Request must be between 1 byte and 2 MiB.'})
            payload = json.loads(self.rfile.read(length))
            import figure_backend
            return self.json_reply(200, figure_backend.render(payload))
        except (ValueError, UnicodeError) as exc:
            return self.json_reply(400, {'ok': False, 'error': str(exc)})
        except Exception as exc:
            return self.json_reply(500, {'ok': False, 'error': str(exc)})

    def end_headers(self):
        # A preview server that caches is a preview server that shows you the
        # file you edited five minutes ago.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format, *args):  # noqa: A002 - signature is the base class's
        if self.server.verbose:
            super().log_message(format, *args)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    verbose = True
    renderer_enabled = True


def serve(root: str, port: int, host: str, verbose: bool, renderer: bool = True) -> int:
    if not os.path.isdir(root):
        print("error: %s is not a directory." % root, file=sys.stderr)
        return 2
    handler = functools.partial(Handler, directory=os.path.abspath(root))
    Server.verbose = verbose
    with Server((host, port), handler) as httpd:
        httpd.renderer_enabled = renderer
        url = "http://%s:%d/" % (host, httpd.server_address[1])
        print("serving %s at %s" % (os.path.relpath(root, REPO_ROOT) or ".", url))
        print("open %sindex.html — Ctrl-C to stop" % url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=DEFAULT_ROOT, help="Directory to serve (default: web/).")
    parser.add_argument("--port", type=int, default=8765, help="Port (default 8765; 0 picks a free one).")
    parser.add_argument("--host", default="127.0.0.1", help="Interface to bind (default loopback).")
    parser.add_argument("--quiet", action="store_true", help="Do not log each request.")
    parser.add_argument('--static-only', action='store_true', help='Disable the local Matplotlib API; use browser Pyodide instead.')
    args = parser.parse_args(argv)
    return serve(args.root, args.port, args.host, not args.quiet, not args.static_only)


if __name__ == "__main__":
    raise SystemExit(main())
