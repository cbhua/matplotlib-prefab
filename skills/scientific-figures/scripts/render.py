"""Render one single-column, single-panel scientific figure from a JSON spec.

Usage::

    python skills/scientific-figures/scripts/render.py \
        --spec tests/data/line-multi.json \
        --output-dir .tmp/figure-preview/line-multi

The command writes five files into the output directory and nothing else:

    figure.pdf            the deliverable, at the exact physical size of the profile
    figure.png            a raster preview at profile.output.png_dpi
    spec.json             the validated input, exactly as drawn
    profile.resolved.json the style profile that produced this figure
    report.json           the deterministic check results

Existing files with those five names are overwritten; every other file in the
directory is left untouched and nothing is deleted.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from typing import Any, Dict, Optional, Sequence

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import figure_core  # noqa: E402
import inspect_figure  # noqa: E402


def load_template(kind: str):
    """Load the template module for ``kind`` from this skill's assets directory."""
    path = os.path.join(SKILL_ROOT, "assets", "templates", "%s.py" % kind)
    if not os.path.isfile(path):
        raise figure_core.SpecError(
            "No template found for kind %r (looked for %s)." % (kind, path)
        )
    spec = importlib.util.spec_from_file_location("scientific_figures_template_%s" % kind, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def render(
    spec_path: str,
    output_dir: str,
    profile_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate, draw, export and check. Returns the report payload."""
    import matplotlib.pyplot as plt

    resolved_profile_path = profile_path or figure_core.default_profile_path(SKILL_ROOT)
    profile = figure_core.load_profile(resolved_profile_path)
    spec = figure_core.load_spec(spec_path)
    template = load_template(spec["kind"])

    os.makedirs(output_dir, exist_ok=True)

    with figure_core.style_context(profile):
        fig, ax = figure_core.create_figure(profile)
        try:
            drawn = template.draw(ax, spec, profile)
            written = figure_core.export_figure(fig, output_dir, profile)
            report = inspect_figure.inspect_render(fig, ax, spec, profile, drawn, output_dir)
        finally:
            plt.close(fig)

    figure_core.write_json(os.path.join(output_dir, "spec.json"), spec)
    figure_core.write_json(os.path.join(output_dir, "profile.resolved.json"), profile)

    report["inputs"] = {
        "spec_source": os.path.abspath(spec_path),
        "profile_source": os.path.abspath(resolved_profile_path),
    }
    report["outputs"] = {
        name: os.path.abspath(path)
        for name, path in list(written.items())
        + [
            ("spec", os.path.join(output_dir, "spec.json")),
            ("profile", os.path.join(output_dir, "profile.resolved.json")),
            ("report", os.path.join(output_dir, "report.json")),
        ]
    }
    report["reproduce"] = (
        "python %s --spec %s --profile %s --output-dir %s"
        % (
            os.path.relpath(os.path.join(SCRIPT_DIR, "render.py")),
            os.path.relpath(os.path.join(output_dir, "spec.json")),
            os.path.relpath(os.path.join(output_dir, "profile.resolved.json")),
            os.path.relpath(output_dir),
        )
    )
    report["drawn"] = drawn

    figure_core.write_json(os.path.join(output_dir, "report.json"), report)
    return report


def _print_summary(report: Dict[str, Any], output_dir: str) -> None:
    counts = report["counts"]
    print("status: %s  (pass %d, warn %d, fail %d, not_checked %d)" % (
        report["status"],
        counts.get("pass", 0),
        counts.get("warn", 0),
        counts.get("fail", 0),
        counts.get("not_checked", 0),
    ))
    for check in report["checks"]:
        if check["status"] in (inspect_figure.FAIL, inspect_figure.WARN, inspect_figure.NOT_CHECKED):
            print("  [%s] %s: %s" % (check["status"], check["id"], check["message"]))
    print("output: %s" % os.path.abspath(output_dir))
    print("preview: %s" % os.path.abspath(os.path.join(output_dir, "figure.png")))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a single-column, single-panel line or bar figure from a JSON spec.",
    )
    parser.add_argument("--spec", required=True, help="Path to the JSON figure spec.")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for figure.pdf, figure.png, spec.json, profile.resolved.json and report.json.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Full style profile to use. Defaults to references/profiles/single-column.json.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full report to stdout instead of a summary.",
    )
    args = parser.parse_args(argv)

    try:
        report = render(args.spec, args.output_dir, args.profile)
    except (figure_core.SpecError, figure_core.ProfileError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_summary(report, args.output_dir)
    return 1 if report["status"] == inspect_figure.FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
