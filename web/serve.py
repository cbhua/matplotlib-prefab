#!/usr/bin/env python3
"""Serve the browser tool over HTTP for local preview.

    python web/serve.py                 # http://127.0.0.1:8765/
    python web/serve.py --port 9000
    python web/serve.py --root .        # repository root, for the test harness

``file://`` will not work and this script does not pretend otherwise: the tool
loads a Web Worker and a WebAssembly module, and browsers refuse both from a
file URL. Any static HTTP server does; this one exists so the repository has a
command that needs nothing installed.

It serves the working tree read-only and binds to the loopback interface. It is
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


def serve(root: str, port: int, host: str, verbose: bool) -> int:
    if not os.path.isdir(root):
        print("error: %s is not a directory." % root, file=sys.stderr)
        return 2
    handler = functools.partial(Handler, directory=os.path.abspath(root))
    Server.verbose = verbose
    with Server((host, port), handler) as httpd:
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
    args = parser.parse_args(argv)
    return serve(args.root, args.port, args.host, not args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
