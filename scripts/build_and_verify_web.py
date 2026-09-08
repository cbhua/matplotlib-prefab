#!/usr/bin/env python3
"""Build the browser tool's assets and produce every piece of evidence, in order.

One command, so that "the site is current" is a thing you can check rather than
a thing you remember. The order matters: the fonts have to exist before a page
can be described, the pages before the browser can show one, and the browser
before anything can be compared with it.

    python scripts/build_and_verify_web.py              # everything
    python scripts/build_and_verify_web.py --fast       # skip the LaTeX stages
    python scripts/build_and_verify_web.py --list       # show the stages

Each stage is a separate script that can be run on its own; this only sequences
them and stops at the first failure, because a later stage's evidence would
otherwise describe a build that did not work.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from typing import List, Optional, Sequence

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = sys.executable

# (id, needs LaTeX, needs a browser, argv, what it produces)
STAGES = [
    ("fetch-runtime", False, False, ["scripts/fetch_pyodide.py"],
     "the pinned Pyodide runtime and wheels in web/public/generated/pyodide/"),
    ("parity-env", False, False, ["scripts/parity.py", "--setup"],
     "a local interpreter matching the versions the browser runs"),
    ("fonts", False, False, ["scripts/build_fonts.py"],
     "the venue body faces as WOFF2, verified against the compiled pages"),
    ("assets", False, False, ["scripts/build_web_assets.py"],
     "copies of the repository's Python, profile and specs, with digests"),
    ("baselines", True, False, ["scripts/calibrate_conference_pages.py", "--generate"],
     "the six venue/width-mode page manifests, measured from compiled LaTeX"),
    ("page-calibration", True, True, ["scripts/calibrate_conference_pages.py", "--compare"],
     "per-run millimetre errors, overlays and difference images for those six pages"),
    ("prototype", False, True, ["scripts/prototype_pyodide.py", "--keep-svg"],
     "cold-start and hot-render measurements for the browser runtime"),
    ("equivalence", False, True, ["scripts/verify_render_equivalence.py", "--keep-svg"],
     "browser-versus-local SVG comparison over the style matrix, and interaction latency"),
    ("export-roundtrip", False, True, ["scripts/verify_export_roundtrip.py"],
     "exports fed back through render.py and compared"),
    ("browsers", False, True, ["scripts/verify_browsers.py"],
     "which browser engines were actually tested here"),
    ("end-to-end", True, True, ["scripts/end_to_end_pages.py", "--tuned"],
     "the full page matrix: browser preview versus a LaTeX page built from its export"),
]


def run(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fast", action="store_true",
                        help="Skip the stages that compile LaTeX.")
    parser.add_argument("--only", action="append", help="Run just this stage (repeatable).")
    parser.add_argument("--skip", action="append", help="Skip this stage (repeatable).")
    parser.add_argument("--list", action="store_true", help="List the stages and exit.")
    args = parser.parse_args(argv)

    if args.list:
        for name, latex, browser, command, produces in STAGES:
            needs = ", ".join(filter(None, ["LaTeX" if latex else "", "browser" if browser else ""]))
            print("%-18s %-16s %s" % (name, "(%s)" % needs if needs else "", produces))
        return 0

    selected = [stage for stage in STAGES
                if (not args.only or stage[0] in args.only)
                and (not args.skip or stage[0] not in args.skip)
                and not (args.fast and stage[1])]
    if not selected:
        print("error: nothing selected.", file=sys.stderr)
        return 2

    failures: List[str] = []
    for name, _latex, _browser, command, produces in selected:
        print("\n=== %s — %s" % (name, produces))
        started = time.perf_counter()
        result = subprocess.run([PYTHON, *command], cwd=REPO_ROOT)
        elapsed = time.perf_counter() - started
        if result.returncode != 0:
            print("!!! %s failed (exit %d) after %.1f s" % (name, result.returncode, elapsed),
                  file=sys.stderr)
            failures.append(name)
            break
        print("--- %s ok in %.1f s" % (name, elapsed))

    print()
    if failures:
        print("stopped at: %s. Nothing after it was run, so the evidence on disk is "
              "incomplete — do not report it as passing." % ", ".join(failures), file=sys.stderr)
        return 1
    print("all %d stage(s) completed. Evidence is under tests/web/calibration/." % len(selected))
    if args.fast:
        print("NOTE: --fast skipped every LaTeX stage, so the calibration and the "
              "end-to-end pages on disk are from a previous run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
