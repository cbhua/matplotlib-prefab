#!/usr/bin/env python3
"""Render one spec/profile pair to SVG and write the result to stdout as JSON.

The equivalence tests need to run the shared drawing code inside a *different*
interpreter — the one pinned to the versions the browser runs — and compare what
comes out with what the browser produced. That means a process boundary, and a
process boundary needs a stable text protocol.

    echo '{"spec": {...}, "profile": {...}}' | python scripts/render_svg_stdio.py

Reads ``{"spec": ..., "profile": ...}`` (either may instead be ``{"path": "..."}``)
and writes ``{"ok": true, "svg": ..., ...}``. It imports nothing but
``figure_core``, so the parity interpreter needs only matplotlib and numpy — no
pytest, no pypdf, no repository package.

This is a test and tooling interface. ``render.py`` remains the deliverable
command and still writes exactly its five files; nothing here changes that.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict

DEFAULT_SKILL_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "skills", "scientific-figures",
)


def resolve(value: Any, what: str) -> Dict[str, Any]:
    """Accept an inline object or ``{"path": ...}`` and return the object."""
    if isinstance(value, dict) and set(value) == {"path"}:
        with open(value["path"], encoding="utf-8") as handle:
            return json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("%s must be a JSON object or {\"path\": ...}" % what)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skill-root", default=DEFAULT_SKILL_ROOT,
                        help="Skill directory holding scripts/ and assets/templates/.")
    args = parser.parse_args()

    scripts = os.path.join(args.skill_root, "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)

    import matplotlib

    matplotlib.use("svg")
    import numpy
    import figure_core

    try:
        request = json.load(sys.stdin)
        spec = resolve(request["spec"], "spec")
        profile = resolve(request["profile"], "profile")
        for key, value in (request.get("profile_overrides") or {}).items():
            section, _, field = key.partition(".")
            profile[section][field] = value
        result = figure_core.render_to_svg(spec, profile, args.skill_root)
    except Exception as exc:
        json.dump({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}, sys.stdout)
        return 2

    json.dump(
        {
            "ok": True,
            "svg": result["svg"],
            "drawn": result["drawn"],
            "width_mm": result["width_mm"],
            "height_mm": result["height_mm"],
            "resolved_profile": result["profile"],
            "environment": {
                "python": sys.version.split()[0],
                "matplotlib": matplotlib.__version__,
                "numpy": numpy.__version__,
                "backend": matplotlib.get_backend(),
                "platform": sys.platform,
            },
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
