"""The browser worker's Python side: turn a request into an SVG, in memory.

This module is deliberately thin. It owns no style numbers, no template and no
layout decision — those are all in ``figure_core`` and the templates, which are
copied into the worker unmodified from ``skills/scientific-figures/``. What lives
here is only what is specific to running inside Pyodide:

* selecting a non-GUI backend before matplotlib is first imported,
* turning a spec/profile pair from JavaScript into a JSON reply,
* turning a validation error into a message the panel can show instead of an
  exception the user cannot act on,
* asking for the live checks, so the preview reports a collision instead of
  silently drawing one,
* releasing the figure after every render, so a worker that has answered a
  thousand slider moves holds no more memory than one that has answered one.

The reply is a JSON string rather than a proxied object: it crosses the
JavaScript boundary by value, so there is no Python object left alive on the
other side to be forgotten.
"""

from __future__ import annotations

import json
import sys
import time
import traceback

import matplotlib

# Must precede the first pyplot import. Pyodide has no display; the SVG backend
# writes the same output the command line does.
matplotlib.use("svg")

import figure_core  # noqa: E402

SKILL_ROOT = "/skill"


def environment():
    """What this worker actually is, for the export hand-off and the reports."""
    import numpy

    return {
        "python": sys.version.split()[0],
        "matplotlib": matplotlib.__version__,
        "numpy": numpy.__version__,
        "backend": matplotlib.get_backend(),
        "platform": sys.platform,
        "renderer": "figure_core.render_to_svg",
        "svg_hashsalt": figure_core.SVG_HASHSALT,
    }


def render(request_json: str) -> str:
    """Render one request. Returns a JSON string; never raises into JavaScript.

    ``request_json`` is ``{"spec": {...}, "profile": {...}}``. Errors come back
    as ``{"ok": false, "error": ...}`` with the validator's own message, because
    "y must be the same length as x" is something the person moving the sliders
    can fix and a traceback is not.
    """
    started = time.perf_counter()
    try:
        request = json.loads(request_json)
        result = figure_core.render_to_svg(
            request["spec"], request["profile"], SKILL_ROOT, checks=True
        )
    except (figure_core.SpecError, figure_core.ProfileError) as exc:
        return json.dumps({
            "ok": False,
            "error": str(exc),
            "error_kind": type(exc).__name__,
        })
    except Exception as exc:  # pragma: no cover - defensive; a bug, not bad input
        return json.dumps({
            "ok": False,
            "error": "%s: %s" % (type(exc).__name__, exc),
            "error_kind": "InternalError",
            "traceback": traceback.format_exc(limit=8),
        })

    return json.dumps({
        "ok": True,
        "svg": result["svg"],
        "drawn": result["drawn"],
        # The live half of render.py's own checks. The panel shows the warnings
        # rather than leaving a crowded figure to speak for itself, and the
        # export carries them so the receiving agent knows what was already
        # known about this configuration.
        "report": result["report"],
        "width_mm": result["width_mm"],
        "height_mm": result["height_mm"],
        "width_in": result["width_in"],
        "height_in": result["height_in"],
        "resolved_profile": result["profile"],
        "resolved_spec": result["spec"],
        "render_ms": round((time.perf_counter() - started) * 1000.0, 2),
    })
