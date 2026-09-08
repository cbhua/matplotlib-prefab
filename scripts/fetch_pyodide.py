#!/usr/bin/env python3
"""Fetch the pinned Pyodide runtime and wheels into the web assets tree.

The published site serves its own copy of everything it runs: the Python
interpreter, matplotlib and every wheel matplotlib needs. Nothing is loaded from
a CDN at page load, so the figure a reader sees is produced by the versions this
repository pinned, not by whatever a CDN is serving today.

    python scripts/fetch_pyodide.py            # download what the lock file names
    python scripts/fetch_pyodide.py --verify   # check what is on disk, download nothing
    python scripts/fetch_pyodide.py --record --pyodide-version 0.28.3

``--record`` is the maintenance path: it resolves matplotlib's dependency
closure out of Pyodide's own ``pyodide-lock.json``, downloads each file, and
writes ``web/pyodide.lock.json`` with a sha256 and a byte count per file. The
ordinary path (no flags) downloads exactly those files and refuses anything
whose digest does not match, so a substituted or truncated wheel is an error
rather than a subtly different figure.

The downloaded tree is large (tens of MB) and is *not* committed; the lock file
is. Run this once before building or serving the site.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(REPO_ROOT, "web")
LOCK_PATH = os.path.join(WEB_DIR, "pyodide.lock.json")
DEST_DIR = os.path.join(WEB_DIR, "public", "generated", "pyodide")

# Pyodide's own runtime files. ``pyodide.mjs`` is the module build the worker
# imports; ``pyodide.js`` is kept because it is the name most documentation uses
# and costs little. ``pyodide-lock.json`` has to be there for Pyodide to resolve
# a package name to a wheel without reaching the network.
RUNTIME_FILES = (
    "pyodide.mjs",
    "pyodide.js",
    "pyodide.asm.js",
    "pyodide.asm.wasm",
    "python_stdlib.zip",
)

# What the browser worker imports. Everything else in the download is a
# dependency Pyodide resolved from this one name.
ROOT_PACKAGES = ("matplotlib",)

DEFAULT_BASE_URL = "https://cdn.jsdelivr.net/pyodide/v%s/full/"


class FetchError(RuntimeError):
    """A download, a digest or the lock file is wrong."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, timeout: int = 300) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return response.read()
    except urllib.error.HTTPError as exc:
        raise FetchError("%s -> HTTP %s" % (url, exc.code)) from None
    except (urllib.error.URLError, OSError) as exc:
        raise FetchError(
            "%s could not be fetched: %s. This step needs network access; the "
            "published site does not." % (url, exc)
        ) from None


# --------------------------------------------------------------------------
# Recording a new lock
# --------------------------------------------------------------------------

def dependency_closure(lock: Dict[str, Any], roots: Sequence[str]) -> List[str]:
    """Every package ``roots`` transitively needs, by Pyodide's own metadata.

    Reading the closure out of the distribution rather than listing wheels by
    hand means a Pyodide upgrade that splits or renames a dependency is picked
    up instead of silently producing a runtime that cannot import matplotlib.
    """
    packages = lock["packages"]
    seen: List[str] = []
    stack = list(roots)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        entry = packages.get(name)
        if entry is None:
            raise FetchError(
                "Pyodide's lock file has no package %r. Its package set changed; "
                "check ROOT_PACKAGES against the new distribution." % name
            )
        seen.append(name)
        stack.extend(entry.get("depends", []))
    return sorted(seen)


def record(version: str, base_url: str, timeout: int) -> Dict[str, Any]:
    print("resolving pyodide %s from %s" % (version, base_url))
    lock_bytes = download(base_url + "pyodide-lock.json", timeout)
    upstream = json.loads(lock_bytes.decode("utf-8"))

    names = dependency_closure(upstream, ROOT_PACKAGES)
    print("matplotlib pulls in %d package(s): %s" % (len(names), ", ".join(names)))

    files: List[Dict[str, Any]] = []

    def add(name: str, payload: bytes, role: str, **extra: Any) -> None:
        files.append(
            {
                "name": name,
                "role": role,
                "sha256": sha256_bytes(payload),
                "bytes": len(payload),
                **extra,
            }
        )

    add("pyodide-lock.json", lock_bytes, "runtime")
    for name in RUNTIME_FILES:
        payload = download(base_url + name, timeout)
        add(name, payload, "runtime")
        print("  runtime %-20s %8.1f KiB" % (name, len(payload) / 1024))

    for name in names:
        entry = upstream["packages"][name]
        file_name = entry["file_name"]
        payload = download(base_url + file_name, timeout)
        add(
            file_name,
            payload,
            "package",
            package=name,
            package_version=entry["version"],
        )
        print("  package %-20s %8.1f KiB  (%s %s)"
              % (file_name[:20], len(payload) / 1024, name, entry["version"]))

    total = sum(item["bytes"] for item in files)
    return {
        "lock_version": "1",
        "note": "Written by scripts/fetch_pyodide.py --record. Every file the browser "
                "runtime needs, pinned by digest. Do not hand-edit: re-record against a "
                "new Pyodide version instead, then re-run the browser parity tests, "
                "because a different matplotlib draws a different SVG.",
        "pyodide_version": version,
        "base_url": base_url,
        "runtime_info": upstream.get("info", {}),
        "root_packages": list(ROOT_PACKAGES),
        "packages": {
            name: upstream["packages"][name]["version"] for name in names
        },
        "total_bytes": total,
        "total_mib": round(total / (1024 * 1024), 2),
        "files": files,
    }


# --------------------------------------------------------------------------
# Fetching against an existing lock
# --------------------------------------------------------------------------

def load_lock() -> Dict[str, Any]:
    if not os.path.isfile(LOCK_PATH):
        raise FetchError(
            "No lock file at %s. Create one with:\n"
            "  python scripts/fetch_pyodide.py --record --pyodide-version <x.y.z>"
            % LOCK_PATH
        )
    with open(LOCK_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def fetch(lock: Dict[str, Any], timeout: int, verify_only: bool) -> int:
    os.makedirs(DEST_DIR, exist_ok=True)
    base_url = lock["base_url"]
    problems = 0
    downloaded = 0
    for entry in lock["files"]:
        destination = os.path.join(DEST_DIR, entry["name"])
        if os.path.isfile(destination) and sha256_file(destination) == entry["sha256"]:
            continue
        if verify_only:
            state = "missing" if not os.path.isfile(destination) else "digest mismatch"
            print("  %-40s %s" % (entry["name"], state), file=sys.stderr)
            problems += 1
            continue
        payload = download(base_url + entry["name"], timeout)
        actual = sha256_bytes(payload)
        if actual != entry["sha256"]:
            raise FetchError(
                "%s came back with sha256 %s but the lock file says %s. Refusing to "
                "write it: the site would then be running code this repository has "
                "not pinned." % (entry["name"], actual, entry["sha256"])
            )
        with open(destination, "wb") as handle:
            handle.write(payload)
        downloaded += 1
        print("  fetched %-40s %8.1f KiB" % (entry["name"], len(payload) / 1024))
    return problems if verify_only else downloaded


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--record", action="store_true",
                        help="Resolve and download a Pyodide version, then write the lock file.")
    parser.add_argument("--pyodide-version", help="Version to record, e.g. 0.28.3.")
    parser.add_argument("--base-url", help="Override the download base URL.")
    parser.add_argument("--verify", action="store_true",
                        help="Report what is missing or wrong on disk and download nothing.")
    parser.add_argument("--timeout", type=int, default=300, help="Seconds per download.")
    args = parser.parse_args(argv)

    try:
        if args.record:
            if not args.pyodide_version:
                parser.error("--record needs --pyodide-version")
            base_url = args.base_url or (DEFAULT_BASE_URL % args.pyodide_version)
            lock = record(args.pyodide_version, base_url, args.timeout)
            os.makedirs(WEB_DIR, exist_ok=True)
            with open(LOCK_PATH, "w", encoding="utf-8") as handle:
                json.dump(lock, handle, indent=2)
                handle.write("\n")
            print("\nwrote %s (%d files, %.1f MiB)"
                  % (os.path.relpath(LOCK_PATH, REPO_ROOT), len(lock["files"]), lock["total_mib"]))
            # Recording downloaded everything already; put it where the site wants it.
            fetch(lock, args.timeout, verify_only=False)
            return 0

        lock = load_lock()
        result = fetch(lock, args.timeout, verify_only=args.verify)
        if args.verify:
            if result:
                print("%d file(s) missing or wrong in %s; run without --verify."
                      % (result, os.path.relpath(DEST_DIR, REPO_ROOT)), file=sys.stderr)
                return 1
            print("pyodide %s: all %d files present and matching."
                  % (lock["pyodide_version"], len(lock["files"])))
            return 0
        print("pyodide %s ready in %s (%d newly fetched, %.1f MiB total)"
              % (lock["pyodide_version"], os.path.relpath(DEST_DIR, REPO_ROOT),
                 result, lock["total_mib"]))
        return 0
    except FetchError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
