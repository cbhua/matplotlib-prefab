#!/usr/bin/env python3
"""The local interpreter that matches what the browser runs, and how to get one.

The tool's whole claim is that a figure previewed in the browser is the figure
``render.py`` produces. That claim is only checkable against a local environment
running the *same* matplotlib the browser runs, because matplotlib's SVG output
legitimately changes between versions. This module owns that environment:

* it reads the pinned versions out of ``web/pyodide.lock.json`` — one source of
  truth, so upgrading Pyodide moves the local twin with it;
* it can create ``.venv-render-parity`` with those versions;
* it renders through ``render_svg_stdio.py`` in that interpreter.

    python scripts/parity.py --setup     # create or refresh the environment
    python scripts/parity.py --status    # say what is there and whether it matches

The repository's ordinary ``.venv`` deliberately tracks a *newer* matplotlib:
that is where the skill's own tests run, and pinning it to the browser's version
would freeze the project on whatever Pyodide happens to ship. The two are
different on purpose, and the parity reports say which one produced which SVG.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, Optional, Sequence

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK_PATH = os.path.join(REPO_ROOT, "web", "pyodide.lock.json")
PARITY_VENV = os.path.join(REPO_ROOT, ".venv-render-parity")
STDIO_SCRIPT = os.path.join(REPO_ROOT, "scripts", "render_svg_stdio.py")

# What the browser actually imports when it draws. pillow, fonttools and the
# rest come along as matplotlib's dependencies; pinning those two is what fixes
# the drawing.
PINNED = ("matplotlib", "numpy")

# Pyodide builds its own CPython for wasm; a local interpreter cannot be that
# exact build. This is the closest widely available one, and the difference is
# recorded in every parity report rather than glossed over.
LOCAL_PYTHON = "3.12"


class ParityError(RuntimeError):
    pass


def pinned_versions() -> Dict[str, str]:
    if not os.path.isfile(LOCK_PATH):
        raise ParityError(
            "No %s. Run scripts/fetch_pyodide.py --record first; the parity environment "
            "is defined by the browser runtime, not the other way round."
            % os.path.relpath(LOCK_PATH, REPO_ROOT)
        )
    with open(LOCK_PATH, encoding="utf-8") as handle:
        lock = json.load(handle)
    packages = lock["packages"]
    missing = [name for name in PINNED if name not in packages]
    if missing:
        raise ParityError("The Pyodide lock file does not pin %s." % ", ".join(missing))
    return {name: packages[name] for name in PINNED}


def browser_python_version() -> Optional[str]:
    with open(LOCK_PATH, encoding="utf-8") as handle:
        return json.load(handle).get("runtime_info", {}).get("python")


def interpreter() -> str:
    return os.path.join(PARITY_VENV, "bin", "python")


def exists() -> bool:
    return os.path.isfile(interpreter())


def installed_versions(python: Optional[str] = None) -> Dict[str, str]:
    python = python or interpreter()
    code = (
        "import json, matplotlib, numpy, sys;"
        "print(json.dumps({'matplotlib': matplotlib.__version__,"
        " 'numpy': numpy.__version__, 'python': sys.version.split()[0]}))"
    )
    result = subprocess.run([python, "-c", code], capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise ParityError(
            "%s could not report its versions: %s" % (python, result.stderr.strip())
        )
    return json.loads(result.stdout)


def matches(python: Optional[str] = None) -> bool:
    try:
        have = installed_versions(python)
    except ParityError:
        return False
    want = pinned_versions()
    return all(have.get(name) == version for name, version in want.items())


def setup(force: bool = False) -> str:
    """Create the parity environment with uv. Idempotent unless ``force``."""
    if shutil.which("uv") is None:
        raise ParityError(
            "uv is not on PATH. Create the environment by hand instead:\n"
            "  python -m venv .venv-render-parity\n"
            "  .venv-render-parity/bin/pip install %s"
            % " ".join("%s==%s" % item for item in sorted(pinned_versions().items()))
        )
    want = pinned_versions()
    if force and os.path.isdir(PARITY_VENV):
        shutil.rmtree(PARITY_VENV)
    if not exists():
        subprocess.run(
            ["uv", "venv", "--python", LOCAL_PYTHON, PARITY_VENV],
            check=True, capture_output=True, text=True, timeout=600,
        )
    requirements = ["%s==%s" % (name, version) for name, version in sorted(want.items())]
    subprocess.run(
        ["uv", "pip", "install", "--python", interpreter(), *requirements],
        check=True, capture_output=True, text=True, timeout=900,
    )
    if not matches():
        raise ParityError(
            "The environment was created but reports %s, not the pinned %s."
            % (installed_versions(), want)
        )
    return interpreter()


def render_svg(
    spec: Dict[str, Any],
    profile: Dict[str, Any],
    python: Optional[str] = None,
    timeout: int = 300,
) -> Dict[str, Any]:
    """Draw in the parity interpreter and hand back its reply."""
    python = python or interpreter()
    if not os.path.isfile(python):
        raise ParityError(
            "No parity interpreter at %s. Run: python scripts/parity.py --setup"
            % os.path.relpath(python, REPO_ROOT)
        )
    result = subprocess.run(
        [python, STDIO_SCRIPT],
        input=json.dumps({"spec": spec, "profile": profile}),
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode not in (0, 2) or not result.stdout.strip():
        raise ParityError(
            "The parity render failed (exit %d): %s" % (result.returncode, result.stderr.strip()[:2000])
        )
    reply = json.loads(result.stdout)
    if not reply.get("ok"):
        raise ParityError("The parity render rejected the input: %s" % reply.get("error"))
    return reply


def status() -> Dict[str, Any]:
    want = pinned_versions()
    report: Dict[str, Any] = {
        "pinned_by": os.path.relpath(LOCK_PATH, REPO_ROOT),
        "browser_versions": {**want, "python": browser_python_version()},
        "parity_venv": os.path.relpath(PARITY_VENV, REPO_ROOT),
        "exists": exists(),
    }
    if exists():
        report["installed"] = installed_versions()
        report["matches"] = matches()
        report["python_differs_from_browser"] = (
            report["installed"]["python"] != report["browser_versions"]["python"]
        )
        report["python_difference_note"] = (
            "Pyodide runs its own CPython build for WebAssembly, so the interpreter "
            "version cannot be matched exactly. matplotlib and numpy are matched, and "
            "those are what draw. Any residual difference shows up as an SVG mismatch "
            "in the equivalence check rather than being assumed away."
        )
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--setup", action="store_true", help="Create or update the environment.")
    parser.add_argument("--force", action="store_true", help="Recreate it from scratch.")
    parser.add_argument("--status", action="store_true", help="Print what is installed, as JSON.")
    args = parser.parse_args(argv)

    try:
        if args.setup:
            path = setup(force=args.force)
            print("parity interpreter: %s" % os.path.relpath(path, REPO_ROOT))
        report = status()
        print(json.dumps(report, indent=2))
        if args.status and not report.get("matches"):
            return 1
        return 0
    except (ParityError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        print("error: %s" % detail, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
