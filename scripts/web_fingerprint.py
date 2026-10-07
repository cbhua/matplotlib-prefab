#!/usr/bin/env python3
"""What every committed piece of web evidence was produced from.

The calibration reports, the equivalence run and the end-to-end pages are all
expensive to produce, so they are generated once and committed. That only works
if a change to something they depend on makes them *fail* rather than quietly
describe a version of the tool that no longer exists. This module is the list of
those dependencies and the digests of them.

``tests/web/test_verification.py`` recomputes this and compares. A mismatch is
"regenerate", not "adjust the test".
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Anything whose change would alter what the browser draws, where the page puts
# it, or which numbers the reports contain.
TRACKED: List[str] = [
    "skills/scientific-figures/scripts/grid_core.py",
    "web/src/setup.js",
    "web/src/wrap-layout.js",
    "web/src/css-paper.js",
    "web/src/reflow-paper.js",
    "web/src/reflow-paper.css",
    "web/src/server-renderer.js",
    "web/reference/reflow-content.json",
    "web/figure_backend.py",
    "web/src/css-paper.css",
    "web/src/figure-view.js",
    "web/src/paper-prose.js",
    "web/presets/papers.json",
    "skills/scientific-figures/scripts/figure_core.py",
    "skills/scientific-figures/scripts/render.py",
    "skills/scientific-figures/scripts/inspect_figure.py",
    "skills/scientific-figures/scripts/evaluate_context.py",
    "skills/scientific-figures/assets/templates/line.py",
    "skills/scientific-figures/assets/templates/bar.py",
    "skills/scientific-figures/references/profiles/single-column.json",
    "web/src/app.js",
    "web/src/paper-page.js",
    "web/src/paper-page.css",
    "web/src/controls.js",
    "web/src/export-config.js",
    "web/src/render-worker.js",
    "web/src/python/worker_render.py",
    "web/pyodide.lock.json",
    "tests/conference_context/wrappers/measure.tex",
    "tests/conference_context/wrappers/iclr2026.tex",
    "tests/conference_context/wrappers/neurips2026.tex",
    "tests/conference_context/wrappers/icml2026.tex",
    "tests/fixtures/article-context/body.tex",
    "tests/fixtures/article-context/references.bib",
    "tests/fixtures/conferences/manifest.json",
    "tests/data/line-multi.json",
    "tests/data/line-single.json",
    "tests/data/line-many.json",
    "tests/data/bar-signed.json",
    "tests/data/bar-positive.json",
]

RERUN = "run `python scripts/build_and_verify_web.py` to regenerate the evidence"


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint() -> Dict[str, Any]:
    files: Dict[str, str] = {}
    for relative in TRACKED:
        path = os.path.join(REPO_ROOT, relative)
        if os.path.isfile(path):
            files[relative] = sha256_file(path)
    return {
        "note": "Digests of everything that would change this report. If any of them no "
                "longer match the files on disk, this report describes a version of the "
                "tool that is no longer here; %s." % RERUN,
        "inputs": files,
    }


def stamp(report: Dict[str, Any]) -> Dict[str, Any]:
    """Attach the fingerprint to a report in place, and return it."""
    report["repository"] = fingerprint()
    return report


def stale(recorded: Dict[str, str]) -> List[str]:
    current = fingerprint()["inputs"]
    return sorted(
        key for key in set(recorded) | set(current)
        if recorded.get(key) != current.get(key)
    )


if __name__ == "__main__":
    print(json.dumps(fingerprint(), indent=2))
