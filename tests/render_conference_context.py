#!/usr/bin/env python3
"""Put the prefab figures into real conference pages and keep the result.

``render_gallery.py`` answers "what does this profile look like?". This answers
the question that actually decides a figure: "what does it look like *on the
page*, at the size the venue gives it, next to the type it will be read
against?" A figure that is fine at 85 mm on its own can lose its tick labels the
moment it is set at half the text width of ICLR's body.

    python tests/render_conference_context.py --all
    python tests/render_conference_context.py --venue iclr2026 --case line-multi
    python tests/render_conference_context.py --venue neurips2026 --case bar-signed \
        --profile my-profile.json

Each case writes three files into ``tests/output/conference-context/<venue>/<case>/``:
``page.pdf`` (one whole body page, uncropped), ``page.png`` (its raster preview)
and ``context-report.json`` (every measurement, with units). The multi-page PDF,
the aux files and the derived profile live in a temporary build directory and do
not survive the run.

This needs LaTeX and poppler; ``render.py`` does not. ``--check-dependencies``
says whether they are here. If they are missing, this script exits non-zero: a
context evaluation that did not happen is not a context evaluation that passed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
SKILL_ROOT = os.path.join(REPO_ROOT, "skills", "scientific-figures")
SCRIPTS_DIR = os.path.join(SKILL_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import evaluate_context  # noqa: E402
import figure_core  # noqa: E402

DATA_DIR = os.path.join(TESTS_DIR, "data")
GALLERY_DIR = os.path.join(TESTS_DIR, "output")
OUTPUT_DIR = os.path.join(GALLERY_DIR, "conference-context")
CONFERENCES_DIR = os.path.join(TESTS_DIR, "fixtures", "conferences")
ARTICLE_DIR = os.path.join(TESTS_DIR, "fixtures", "article-context")
WRAPPERS_DIR = os.path.join(TESTS_DIR, "conference_context", "wrappers")
DIAGNOSTICS_DIR = os.path.join(REPO_ROOT, ".tmp", "conference-context-failures")

VENUES = ("iclr2026", "neurips2026", "icml2026")

# The two prefab cases worth carrying into a page: a multi-series line chart,
# where the legend and the dash/marker channel have the most to lose from being
# shrunk, and a signed bar chart, where the category labels do.
WIDTH_CASES = {
    "line-multi": "Three series, a legend and dense tick labels — the case where a "
                  "width reduction shows up first.",
    "bar-signed": "Bars crossing zero with named categories — the case where the "
                  "category labels run out of room first.",
}

# One deliberately mismatched case. The figure is the committed 85 mm render,
# dropped into a half-width ICLR slot without being redrawn, so the report has to
# show a real reduction instead of claiming the type is still 9 pt. It is here to
# prove the measurement detects scaling, not to pass a legibility bar.
REGRESSION_CASE = "line-multi-at-85mm"
REGRESSION_VENUE = "iclr2026"
REGRESSION_SOURCE = os.path.join(GALLERY_DIR, "line-multi")
REGRESSION_NOTE = (
    "Regression case: the committed 85 mm figure placed into ICLR's half-width slot "
    "with no re-render. Expected to warn — it exists to show the scale factor and the "
    "reduced effective type sizes are really measured, not assumed."
)

PNG_DPI = 200

# Everything whose change would make a committed page stale. The freshness test
# compares these against what the reports were built from.
IMPLEMENTATION_FILES = (
    os.path.join("skills", "scientific-figures", "scripts", "evaluate_context.py"),
    os.path.join("skills", "scientific-figures", "scripts", "render.py"),
    os.path.join("skills", "scientific-figures", "scripts", "figure_core.py"),
    os.path.join("skills", "scientific-figures", "scripts", "inspect_figure.py"),
    os.path.join("skills", "scientific-figures", "assets", "templates", "line.py"),
    os.path.join("skills", "scientific-figures", "assets", "templates", "bar.py"),
    os.path.join("tests", "conference_context", "wrappers", "measure.tex"),
    os.path.join("tests", "fixtures", "article-context", "body.tex"),
    os.path.join("tests", "fixtures", "article-context", "references.bib"),
    os.path.join("tests", "fixtures", "conferences", "manifest.json"),
)

RERUN = "run `python tests/render_conference_context.py --all` to regenerate"


# --------------------------------------------------------------------------
# The matrix
# --------------------------------------------------------------------------

def case_ids():
    """Every (venue, case) this script manages, in a stable order."""
    pairs = [(venue, case) for venue in VENUES for case in sorted(WIDTH_CASES)]
    pairs.append((REGRESSION_VENUE, REGRESSION_CASE))
    return pairs


def known_cases():
    return sorted(WIDTH_CASES) + [REGRESSION_CASE]


def case_output_dir(venue, case):
    return os.path.join(OUTPUT_DIR, venue, case)


def spec_path(case):
    return os.path.join(DATA_DIR, "%s.json" % case)


# --------------------------------------------------------------------------
# Freshness fingerprint
# --------------------------------------------------------------------------

def _key(path):
    """Repository-relative where possible, absolute otherwise.

    ``--profile`` can point outside the repository, and ``os.path.relpath`` would
    turn that into a wall of ``../``. An absolute path is both shorter and more
    honest about where the input actually came from.
    """
    path = os.path.abspath(path)
    if os.path.commonpath([path, REPO_ROOT]) == REPO_ROOT:
        return os.path.relpath(path, REPO_ROOT).replace(os.sep, "/")
    return path


def fingerprint(venue, case, profile_path):
    """The inputs this page was built from, as paths and digests.

    Committed under ``repository.inputs`` in every report so that a change to a
    template, a wrapper, the body text, a spec, the profile or the rendering code
    can be *detected* rather than assumed away. Comparing only the default
    profile would miss the point here: these pages are rendered at a derived
    width, so the default profile's digest is one input among several.
    """
    files = {}
    for relative in IMPLEMENTATION_FILES:
        path = os.path.join(REPO_ROOT, relative)
        if os.path.isfile(path):
            files[relative.replace(os.sep, "/")] = evaluate_context.sha256_file(path)

    wrapper = os.path.join(WRAPPERS_DIR, "%s.tex" % venue)
    files[_key(wrapper)] = evaluate_context.sha256_file(wrapper)

    with open(os.path.join(CONFERENCES_DIR, "manifest.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)
    entry = next(item for item in manifest["venues"] if item["id"] == venue)
    for item in entry["files"]:
        path = os.path.join(CONFERENCES_DIR, venue, item["path"])
        files[_key(path)] = evaluate_context.sha256_file(path)

    if case == REGRESSION_CASE:
        for name in ("figure.pdf", "profile.resolved.json", "spec.json"):
            path = os.path.join(REGRESSION_SOURCE, name)
            if os.path.isfile(path):
                files[_key(path)] = evaluate_context.sha256_file(path)
    else:
        for path in (spec_path(case), profile_path):
            files[_key(path)] = evaluate_context.sha256_file(path)

    return {
        "note": "Digests of everything that would change this page. If any of them no "
                "longer match the files on disk, the committed page is stale; %s." % RERUN,
        "inputs": dict(sorted(files.items())),
    }


# --------------------------------------------------------------------------
# Running one case
# --------------------------------------------------------------------------

def fixtures():
    return evaluate_context.Fixtures(
        conferences=CONFERENCES_DIR,
        article=ARTICLE_DIR,
        wrappers=WRAPPERS_DIR,
    )


def run_case(venue, case, profile_path, png_dpi=PNG_DPI):
    output_dir = case_output_dir(venue, case)
    common = dict(
        fixtures=fixtures(),
        venue_id=venue,
        case_id=case,
        output_dir=output_dir,
        png_dpi=png_dpi,
        diagnostics_dir=DIAGNOSTICS_DIR,
    )
    if case == REGRESSION_CASE:
        if not os.path.isfile(os.path.join(REGRESSION_SOURCE, "figure.pdf")):
            raise evaluate_context.ContextError(
                "The regression case needs the committed render in %s; run "
                "`python tests/render_gallery.py` first." % REGRESSION_SOURCE
            )
        report = evaluate_context.evaluate(figure_dir=REGRESSION_SOURCE, **common)
    else:
        report = evaluate_context.evaluate(
            spec_path=spec_path(case), base_profile_path=profile_path, **common
        )

    report["repository"] = fingerprint(venue, case, profile_path)
    report["case_note"] = REGRESSION_NOTE if case == REGRESSION_CASE else WIDTH_CASES[case]
    figure_core.write_json(os.path.join(output_dir, "context-report.json"), report)
    return report


# --------------------------------------------------------------------------
# The index
# --------------------------------------------------------------------------

def write_index(results):
    lines = [
        "# Figures in real conference pages",
        "",
        "Generated by `tests/render_conference_context.py`. **Do not edit by hand.**",
        "",
        "Each entry below is one whole body page of a conference template with a figure",
        "from `tests/data/` set into it — the venue's own margins, running head, folio,",
        "caption style and body type, at the width the template gives a figure. This is",
        "the size a reader meets the figure at; `tests/output/index.md` shows the figures",
        "on their own, which is a different question.",
        "",
        "The PNGs are %d DPI rasters and your viewer will scale them to fit, so **do not**"
        % PNG_DPI,
        "judge printed size from them. The physical numbers in the table are measured",
        "from the compiled PDF's own drawing transform; open `page.pdf` at 100% to see",
        "the real thing.",
        "",
        "The style values these pages were produced with are still *provisional* project",
        "choices, not venue requirements. The body text is an excerpt reproduced as",
        "typographic context and credited in",
        "[`tests/fixtures/article-context/provenance.md`](../../fixtures/article-context/provenance.md);",
        "the figures are synthetic evaluation data. None of these pages is a paper, a",
        "submission or an accepted work.",
        "",
        "## Summary",
        "",
        "| Venue | Case | Line width | Target | Drawn | Scale | Body / caption pt | Page | Status |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in results:
        report = item["report"]
        template = report["template"]
        geometry = report["geometry"]
        lines.append(
            "| %s | [`%s`](%s/%s/) | %.2f mm | %.2f mm | %.2f mm | %.4f | %s / %s | %d of %d | %s |"
            % (
                report["venue"]["name"],
                report["case"],
                report["venue"]["id"],
                report["case"],
                template["float_linewidth_mm"],
                geometry["target_width_mm"],
                geometry["placed_width_mm"],
                geometry["scale"],
                template["body_font_size_pt"],
                template["caption_font_size_pt"],
                report["page"]["printed_page_number"] or -1,
                report["page"]["total_pages_in_full_document"],
                report["status"],
            )
        )

    lines += [
        "",
        "`visual_review` is `not_checked` in every report and stays that way until a",
        "person opens the PNG. A clean compile is not a legible figure.",
        "",
    ]

    for item in results:
        report = item["report"]
        venue = report["venue"]
        case = report["case"]
        geometry = report["geometry"]
        template = report["template"]
        rel = "%s/%s" % (venue["id"], case)
        lines += [
            "## %s — %s" % (venue["name"], case),
            "",
            report["case_note"],
            "",
            "%s body, `%s` mode, %d column(s). Figure width rule: %s."
            % (venue["name"], venue["mode"], venue["columns"], venue["target_width_rule"]),
            "",
            "| Measurement | Value | Where it came from |",
            "| --- | --- | --- |",
            "| text width | %.2f mm | `\\textwidth`, measured by TeX in the document |"
            % template["textwidth_mm"],
            "| column width | %.2f mm | `\\columnwidth`, same |" % template["columnwidth_mm"],
            "| line width at the float | %.2f mm | `\\linewidth` inside the figure |"
            % template["float_linewidth_mm"],
            "| target width | %.2f mm | line width x %s |"
            % (geometry["target_width_mm"], venue["target_width_factor"]),
            "| source figure width | %.2f mm | the figure PDF's media box |"
            % geometry["source_pdf_width_mm"],
            "| drawn width | %.2f mm | the page's drawing transform |" % geometry["placed_width_mm"],
            "| scale | %.4f | drawn / source |" % geometry["scale"],
            "| body type | %s pt | `\\f@size` in body text |" % template["body_font_size_pt"],
            "| caption type | %s pt | `\\f@size` inside the caption |"
            % template["caption_font_size_pt"],
        ]
        effective = report["type_sizes"]["figure_effective_pt"]
        source = report["type_sizes"]["figure_source_pt"]
        if effective and source:
            lines += [
                "| figure axis labels | %.1f pt drawn -> **%.2f pt** printed | source x scale |"
                % (source["axis_label_pt"], effective["axis_label_pt"]),
                "| figure tick labels | %.1f pt drawn -> **%.2f pt** printed | source x scale |"
                % (source["tick_pt"], effective["tick_pt"]),
                "| figure data lines | %.2f pt drawn -> **%.3f pt** printed | source x scale |"
                % (source["data_linewidth_pt"], effective["data_linewidth_pt"]),
            ]
        else:
            lines.append("| figure type sizes | not checked | the figure arrived without a profile |")
        lines += [
            "",
            "Checks: %d pass, %d warn, %d fail, %d not checked."
            % (
                report["counts"]["pass"],
                report["counts"]["warn"],
                report["counts"]["fail"],
                report["counts"]["not_checked"],
            ),
            "",
        ]
        # `figure_render_checks` is broken out one-per-check just below, so its
        # single run-on summary line would only be noise here.
        noisy = [
            entry for entry in report["checks"]
            if entry["status"] in ("warn", "fail") and entry["id"] != "figure_render_checks"
        ]
        lines += ["* **%s** — `%s`: %s" % (entry["status"], entry["id"], entry["message"])
                  for entry in noisy]
        if noisy:
            lines.append("")
        render_checks = report["figure_source"].get("figure_checks") or []
        if render_checks:
            lines += [
                "What `render.py` itself said about the figure **at this width** — these",
                "are the ones to look at on the page:",
                "",
            ]
            lines += [
                "* `%s` (%s): %s" % (entry["id"], entry["status"], entry["message"])
                for entry in render_checks
            ]
            lines.append("")
        lines += [
            "![%s %s](%s/page.png)" % (venue["id"], case, rel),
            "",
            "PDF: [`%s/page.pdf`](%s/page.pdf) · Report: [`%s/context-report.json`](%s/context-report.json)"
            % (rel, rel, rel, rel),
            "",
        ]

    path = os.path.join(OUTPUT_DIR, "index.md")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines).rstrip() + "\n")
    return path


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--all", action="store_true", help="Run the whole matrix and rewrite the index.")
    parser.add_argument("--venue", action="append", help="Restrict to this venue (repeatable).")
    parser.add_argument("--case", action="append", help="Restrict to this case (repeatable).")
    parser.add_argument(
        "--profile",
        default=figure_core.default_profile_path(SKILL_ROOT),
        help="Profile to derive the target width from. Defaults to the skill's own. "
             "Ignored by the regression case, which places an already-rendered figure.",
    )
    parser.add_argument("--png-dpi", type=int, default=PNG_DPI, help="Preview DPI (default %d)." % PNG_DPI)
    parser.add_argument("--list", action="store_true", help="Print the matrix and exit.")
    parser.add_argument(
        "--check-dependencies",
        action="store_true",
        help="Say whether LaTeX and poppler are available; exit 0 if so, 3 if not.",
    )
    args = parser.parse_args(argv)

    if args.list:
        for venue, case in case_ids():
            print("%s\t%s" % (venue, case))
        return 0

    if args.check_dependencies:
        return evaluate_context.main(["--check-dependencies"])

    if not (args.all or args.venue or args.case):
        parser.error("nothing selected: pass --all, or --venue/--case")

    unknown_venues = sorted(set(args.venue or []) - set(VENUES))
    if unknown_venues:
        print("error: unknown venue(s): %s" % ", ".join(unknown_venues), file=sys.stderr)
        print("known venues: %s" % ", ".join(VENUES), file=sys.stderr)
        return 2
    unknown_cases = sorted(set(args.case or []) - set(known_cases()))
    if unknown_cases:
        print("error: unknown case(s): %s" % ", ".join(unknown_cases), file=sys.stderr)
        print("known cases: %s" % ", ".join(known_cases()), file=sys.stderr)
        return 2

    selected = [
        (venue, case)
        for venue, case in case_ids()
        if (not args.venue or venue in args.venue) and (not args.case or case in args.case)
    ]
    if not selected:
        print("error: that venue/case combination is not in the matrix.", file=sys.stderr)
        print("known combinations:", file=sys.stderr)
        for venue, case in case_ids():
            print("  %s %s" % (venue, case), file=sys.stderr)
        return 2

    absent = evaluate_context.missing_tools()
    if absent:
        print("error: the context evaluation cannot run without %s." % ", ".join(sorted(absent)), file=sys.stderr)
        print(evaluate_context.INSTALL_HINT, file=sys.stderr)
        print(
            "\nNothing was written. A context evaluation that did not run is not one that "
            "passed — do not report these pages as verified.",
            file=sys.stderr,
        )
        return 3

    results = []
    worst = "pass"
    for venue, case in selected:
        try:
            report = run_case(venue, case, args.profile, png_dpi=args.png_dpi)
        except (evaluate_context.ContextError, figure_core.SpecError, figure_core.ProfileError) as exc:
            print("%-12s %-22s FAILED\n    %s" % (venue, case, exc), file=sys.stderr)
            return 1
        results.append({"venue": venue, "case": case, "report": report})
        counts = report["counts"]
        print(
            "%-12s %-22s %-5s  drawn %6.2f mm  scale %.4f  page %s  (pass %d warn %d fail %d)"
            % (
                venue,
                case,
                report["status"],
                report["geometry"]["placed_width_mm"],
                report["geometry"]["scale"],
                report["page"]["printed_page_number"],
                counts["pass"],
                counts["warn"],
                counts["fail"],
            )
        )
        for entry in report["checks"]:
            if entry["status"] in ("warn", "fail"):
                print("    [%s] %s: %s" % (entry["status"], entry["id"], entry["message"]))
        if report["status"] == "fail" or (report["status"] == "warn" and worst == "pass"):
            worst = report["status"]

    if len(selected) == len(case_ids()):
        index_path = write_index(results)
        print()
        print("index: %s" % os.path.relpath(index_path, REPO_ROOT))
    else:
        print()
        print("index not rewritten: it covers the whole matrix, so run --all to refresh it.")

    print("Now open the PNGs. `visual_review` stays open until a person does.")
    return 1 if worst == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
