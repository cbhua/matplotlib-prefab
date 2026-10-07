#!/usr/bin/env python3
"""Copy the repository's own rendering code, profile and specs into web/public/generated/.

The browser tool must draw with *this* repository's code, not with a second
implementation that happens to look the same. So nothing under
``web/public/generated/`` is hand-written: this script copies the real files and
records a sha256 for each one. ``tests/web/test_web_assets.py`` re-computes those
digests against the repository and fails when they drift, which is what stops a
site from being published against a stale copy of ``figure_core.py``.

    python scripts/build_web_assets.py            # copy and write the manifest
    python scripts/build_web_assets.py --check    # fail if the copies are stale

The Pyodide runtime is fetched separately by ``scripts/fetch_pyodide.py``; it is
pinned by its own lock file and is not a copy of anything in this repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_ROOT = os.path.join(REPO_ROOT, "skills", "scientific-figures")
WEB_DIR = os.path.join(REPO_ROOT, "web")
GENERATED = os.path.join(WEB_DIR, "public", "generated")
PYTHON_DIR = os.path.join(GENERATED, "python")
MANIFEST_PATH = os.path.join(GENERATED, "assets-manifest.json")

# The Python tree is mirrored with the skill's own directory shape, because
# figure_core.load_template() looks for <skill_root>/assets/templates/<kind>.py.
# Reproducing the layout means the browser runs the unmodified file; flattening
# it would mean patching the loader, i.e. a second code path.
PYTHON_COPIES = (
    ("skills/scientific-figures/scripts/grid_core.py", "python/skill/scripts/grid_core.py"),
    ("skills/scientific-figures/scripts/figure_core.py", "python/skill/scripts/figure_core.py"),
    ("skills/scientific-figures/scripts/inspect_figure.py", "python/skill/scripts/inspect_figure.py"),
    ("skills/scientific-figures/assets/templates/line.py", "python/skill/assets/templates/line.py"),
    ("skills/scientific-figures/assets/templates/scatter.py", "python/skill/assets/templates/scatter.py"),
    ("skills/scientific-figures/assets/templates/bar.py", "python/skill/assets/templates/bar.py"),
    ("web/src/python/worker_render.py", "python/worker_render.py"),
)

PROFILE_COPIES = (
    ("skills/scientific-figures/references/profiles/single-column.json",
     "profiles/single-column.json"),
)

# The specs the tool offers as examples. Small enough that the exported
# hand-off can carry the data inline, which is the point: a reproduction should
# not depend on a file the receiving agent cannot see.
SPEC_COPIES = tuple(
    ("tests/data/%s.json" % name, "specs/%s.json" % name)
    for name in ("line-multi", "line-single", "line-many", "bar-positive", "bar-signed", "scatter")
)

ALL_COPIES = PYTHON_COPIES + PROFILE_COPIES + SPEC_COPIES


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def entries() -> List[Dict[str, Any]]:
    """One record per copied file: where it came from and what it hashed to."""
    records = []
    for source, target in ALL_COPIES:
        absolute = os.path.join(REPO_ROOT, source)
        if not os.path.isfile(absolute):
            raise SystemExit("error: %s does not exist; nothing to copy." % source)
        records.append(
            {
                "source": source,
                "target": target,
                "sha256": sha256_file(absolute),
                "bytes": os.path.getsize(absolute),
            }
        )
    return records


def build(check_only: bool) -> int:
    records = entries()
    stale: List[str] = []

    for record in records:
        source = os.path.join(REPO_ROOT, record["source"])
        target = os.path.join(GENERATED, record["target"])
        if check_only:
            if not os.path.isfile(target) or sha256_file(target) != record["sha256"]:
                stale.append(record["target"])
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(source, target)

    manifest = {
        "manifest_version": "1",
        "note": "Written by scripts/build_web_assets.py. Every file here is a copy of a "
                "repository file, listed with the digest it was copied from. Editing a "
                "copy instead of its source makes the site and the command line disagree; "
                "the web tests fail when they do.",
        "generated_from": "the working tree, not a release",
        "files": records,
        "python_import_root": "python/skill/scripts",
        "python_skill_root": "python/skill",
    }

    if check_only:
        current: Dict[str, Any] = {}
        if os.path.isfile(MANIFEST_PATH):
            with open(MANIFEST_PATH, encoding="utf-8") as handle:
                current = json.load(handle)
        if current.get("files") != records:
            stale.append("assets-manifest.json")
        if stale:
            print("stale web assets: %s" % ", ".join(sorted(set(stale))), file=sys.stderr)
            print("run: python scripts/build_web_assets.py", file=sys.stderr)
            return 1
        print("web assets match the repository (%d files)." % len(records))
        return 0

    os.makedirs(GENERATED, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    print("copied %d file(s) into %s" % (len(records), os.path.relpath(GENERATED, REPO_ROOT)))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="Do not copy; exit non-zero if the copies are stale.")
    args = parser.parse_args(argv)
    return build(args.check)


if __name__ == "__main__":
    raise SystemExit(main())
