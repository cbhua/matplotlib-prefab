"""The conference context evaluation: its fixtures, its arithmetic, and its pages.

Three layers, because they cost three very different things:

* **Fixture and logic tests** run anywhere. They check that the templates are the
  ones the manifest says, that the wrappers ask for camera-ready layout, that
  every citation in the body excerpt has a real bibliography entry, and that the
  PDF geometry maths is right.
* **Committed-artifact tests** read ``tests/output/conference-context/`` and check
  the whole matrix — all seven pages — against the inputs they were built from.
  These are what make the committed pages trustworthy without a LaTeX install.
* **Integration tests**, marked ``conference_context``, actually compile. They
  need LaTeX and poppler and are skipped without them.

The skip is the honest kind: it says the check did not run. Running
``tests/render_conference_context.py`` on a machine without the toolchain exits
non-zero rather than skipping, because *asking for* the evaluation and not
getting it is a failure.
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

import evaluate_context
import figure_core
import render_conference_context as rcc
from conftest import REPO_ROOT, SKILL_ROOT

DEFAULT_PROFILE = figure_core.default_profile_path(SKILL_ROOT)
DELIVERABLES = ("page.pdf", "page.png", "context-report.json")
RERUN = rcc.RERUN

HAVE_TOOLCHAIN = not evaluate_context.missing_tools()
needs_latex = pytest.mark.skipif(
    not HAVE_TOOLCHAIN,
    reason="needs latexmk, pdflatex, bibtex and pdftoppm: %s missing"
    % ", ".join(sorted(evaluate_context.missing_tools())),
)


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def tex_code(path):
    """The file with its comment lines dropped.

    These fixtures explain themselves at length in `%` comments, and those
    comments name the very things the tests forbid ("no \\usepackage here",
    "never figure*"). Assertions run against the code, not the prose about it.
    """
    return "\n".join(
        line for line in read(path).splitlines() if not line.lstrip().startswith("%")
    )


def report_for(venue, case):
    return load(os.path.join(rcc.case_output_dir(venue, case), "context-report.json"))


# ==========================================================================
# Fixtures: the templates are the venues' own, unedited
# ==========================================================================

def test_manifest_lists_every_file_that_is_there_and_nothing_else():
    manifest = load(os.path.join(rcc.CONFERENCES_DIR, "manifest.json"))
    assert {entry["id"] for entry in manifest["venues"]} == set(rcc.VENUES)

    for entry in manifest["venues"]:
        venue_dir = os.path.join(rcc.CONFERENCES_DIR, entry["id"])
        listed = {item["path"] for item in entry["files"]}
        on_disk = set(os.listdir(venue_dir))
        assert listed == on_disk, (
            "%s: manifest lists %s but the directory holds %s"
            % (entry["id"], sorted(listed), sorted(on_disk))
        )


@pytest.mark.parametrize("venue", rcc.VENUES)
def test_template_files_are_byte_for_byte_what_the_manifest_recorded(venue):
    """A template edited to suit a figure would invalidate every page here."""
    manifest = load(os.path.join(rcc.CONFERENCES_DIR, "manifest.json"))
    entry = next(item for item in manifest["venues"] if item["id"] == venue)
    for item in entry["files"]:
        path = os.path.join(rcc.CONFERENCES_DIR, venue, item["path"])
        assert evaluate_context.sha256_file(path) == item["sha256"], (
            "%s/%s no longer matches the digest recorded when it was copied from the "
            "venue archive. The templates are not ours to edit; re-copy it, or record "
            "why it changed." % (venue, item["path"])
        )


def test_manifest_records_where_the_templates_came_from():
    manifest = load(os.path.join(rcc.CONFERENCES_DIR, "manifest.json"))
    archives = {entry["archive"] for entry in manifest["sources"]}
    assert len(archives) == 4
    for entry in manifest["sources"]:
        assert len(entry["sha256"]) == 64
        assert entry["bytes"] > 0


@pytest.mark.parametrize("venue", rcc.VENUES)
def test_venue_declares_a_camera_ready_mode_and_a_width_rule(venue):
    entry = load(os.path.join(rcc.CONFERENCES_DIR, "manifest.json"))
    entry = next(item for item in entry["venues"] if item["id"] == venue)
    assert entry["mode"] in ("finalcopy", "final", "accepted")
    assert entry["mode_source"].strip()
    assert entry["target_width_factor"] in (0.5, 1.0)
    # A two-column venue gets a whole column, not half the text width: the column
    # separation is already out of \columnwidth.
    if entry["columns"] == 2:
        assert entry["target_width_factor"] == 1.0
    else:
        assert entry["target_width_factor"] == 0.5


@pytest.mark.parametrize("venue", rcc.VENUES)
def test_wrapper_uses_the_declared_mode_and_says_it_is_a_fixture(venue):
    path = os.path.join(rcc.WRAPPERS_DIR, "%s.tex" % venue)
    source = read(path)
    code = tex_code(path)
    manifest = load(os.path.join(rcc.CONFERENCES_DIR, "manifest.json"))
    entry = next(item for item in manifest["venues"] if item["id"] == venue)

    switch = {"iclr2026": r"\iclrfinalcopy",
              "neurips2026": "[main, final]{neurips_2026}",
              "icml2026": "[accepted]{icml2026}"}[venue]
    assert switch in code, "%s does not use the camera-ready mode the manifest declares" % venue
    assert entry["mode"] in source or switch in code

    assert r"\input{measure}" in code
    assert r"\input{body}" in code
    # Nothing on the typeset page may claim it is a real paper.
    assert "not a submission" in code
    assert "fixture" in code.lower()
    # Two-column venue must not reach for figure*.
    assert "figure*" not in code


def test_wrappers_exist_for_exactly_the_venues_in_the_matrix():
    on_disk = {
        os.path.splitext(name)[0]
        for name in os.listdir(rcc.WRAPPERS_DIR)
        if name.endswith(".tex") and name != "measure.tex"
    }
    assert on_disk == set(rcc.VENUES)


def test_wrappers_do_not_touch_the_page_geometry():
    """The fixture may not make the page fit the figure."""
    forbidden = (
        r"\textwidth", r"\columnwidth", r"\oddsidemargin", r"\evensidemargin",
        r"\topmargin", r"\textheight", r"\columnsep", r"\baselineskip",
        "geometry}", r"\small", r"\footnotesize",
    )
    for name in os.listdir(rcc.WRAPPERS_DIR):
        if not name.endswith(".tex") or name == "measure.tex":
            continue
        body = tex_code(os.path.join(rcc.WRAPPERS_DIR, name))
        for token in forbidden:
            assert token not in body, (
                "%s sets %s. The template decides the page; the fixture does not get to "
                "widen it to suit a figure." % (name, token)
            )


# ==========================================================================
# The body-text fixture
# ==========================================================================

def test_body_fixture_is_venue_neutral_and_pulls_in_the_figure():
    source = tex_code(rcc.fixtures().body_path)
    for token in (r"\documentclass", r"\usepackage", r"\begin{document}", "nips_2017"):
        assert token not in source, "body.tex must carry no preamble of its own (%s)" % token
    assert r"\input{context-figure}" in source
    assert r"\section{" in source
    assert r"\label{sec:attention}" in source and r"\ref{sec:attention}" in source
    assert "$h_t$" in source, "the excerpt should keep real inline maths"
    assert source.count(r"\citep") >= 6, "an excerpt with no citations is not a body page"


def test_every_citation_key_has_a_real_bibliography_entry():
    import re

    body = tex_code(rcc.fixtures().body_path)
    bib = read(rcc.fixtures().bib_path)
    defined = set(re.findall(r"^@\w+\{([^,]+),", bib, re.M))
    used = set()
    for group in re.findall(r"\\citep\{([^}]*)\}", body):
        used.update(key.strip() for key in group.split(",") if key.strip())

    assert used, "no citations found in the excerpt"
    assert used <= defined, (
        "citation key(s) with no entry: %s. Add a verified entry — do not define the "
        "key away." % ", ".join(sorted(used - defined))
    )


def test_bibliography_entries_are_not_stubs():
    import re

    bib = read(rcc.fixtures().bib_path)
    entries = re.findall(r"@\w+\{[^,]+,(.*?)\n}", bib, re.S)
    assert len(entries) >= 20
    for entry in entries:
        assert "title" in entry and "author" in entry and "year" in entry, (
            "an entry is missing title/author/year; a placeholder reference is a "
            "fabricated one"
        )


def test_provenance_names_the_source_and_the_edits():
    path = os.path.join(rcc.ARTICLE_DIR, "provenance.md")
    assert os.path.isfile(path)
    text = read(path)
    assert "1706.03762" in text, "the excerpt's source article must be identified"
    assert "attn_is_all_u_need.tar.gz" in text
    for source_file in ("introduction.tex", "background.tex", "model_architecture.tex"):
        assert source_file in text, "provenance must say which files the excerpt came from"
    assert r"\clearpage" in text, "the inserted page break is a fixture edit and must be recorded"


# ==========================================================================
# Logic that does not need a compiler
# ==========================================================================

def test_matrix_is_three_venues_two_cases_plus_one_regression():
    pairs = rcc.case_ids()
    assert len(pairs) == 7
    width_pairs = [(venue, case) for venue, case in pairs if case in rcc.WIDTH_CASES]
    assert len(width_pairs) == 6
    assert {venue for venue, _ in width_pairs} == set(rcc.VENUES)
    assert (rcc.REGRESSION_VENUE, rcc.REGRESSION_CASE) in pairs


def test_matrix_cases_are_real_prefab_specs():
    import render_gallery

    for case in rcc.WIDTH_CASES:
        assert case in render_gallery.CASES
        assert os.path.isfile(rcc.spec_path(case))


@pytest.mark.parametrize(
    "factor,expected",
    [(0.5, r"\includegraphics[width=0.5\linewidth]{figure}"),
     (1.0, r"\includegraphics[width=\linewidth]{figure}")],
)
def test_figure_block_asks_for_a_fraction_of_the_line_width(factor, expected):
    """The width is the template's own arithmetic, not a number we computed."""
    block = evaluate_context.figure_block(factor, "caption", placeholder=False)
    assert expected in block
    assert r"\mpfprobebody" in block
    assert r"\mpfprobefloat" in block
    assert r"\label{%s}" % evaluate_context.FIGURE_LABEL in block
    assert "figure*" not in block


def test_probe_block_needs_no_image_on_disk():
    block = evaluate_context.figure_block(0.5, "caption", placeholder=True)
    assert r"\rule{0.5\linewidth}" in block
    assert "includegraphics" not in block


def test_caption_text_is_escaped_before_it_reaches_tex():
    hostile = r"x_1 \newcommand{\z}{} 100% $a$ #1 &"
    escaped = evaluate_context.escape_tex(hostile)
    assert r"\newcommand" not in escaped
    assert r"\textbackslash{}" in escaped
    assert r"\%" in escaped and r"\_" in escaped and r"\$" in escaped and r"\#" in escaped


def test_default_caption_says_the_data_is_synthetic():
    venue = rcc.fixtures().venue("iclr2026")
    caption = evaluate_context.default_caption(venue, "line-multi", "line-multi.json")
    assert "Synthetic" in caption and "not a result" in caption


def test_unit_conversions_keep_tex_and_pdf_points_apart():
    # 1 inch: 72.27 TeX pt, 72 PDF pt, both 25.4 mm.
    assert evaluate_context.tex_pt_to_mm(72.27) == pytest.approx(25.4, abs=1e-9)
    assert evaluate_context.pdf_pt_to_mm(72.0) == pytest.approx(25.4, abs=1e-9)
    # And they are genuinely different: a 5.5 in text width is 397.48 TeX pt.
    assert evaluate_context.tex_pt_to_mm(397.48) == pytest.approx(139.7, abs=0.01)
    assert evaluate_context.pdf_pt_to_mm(397.48) != pytest.approx(139.7, abs=0.01)


def test_matrix_maths_matches_the_pdf_specification():
    # cm concatenates the new matrix onto the CTM: CTM' = M x CTM.
    scale = [2.0, 0.0, 0.0, 3.0, 0.0, 0.0]
    translate = [1.0, 0.0, 0.0, 1.0, 10.0, 20.0]
    combined = evaluate_context._mat_mul(scale, translate)
    assert combined == pytest.approx([2.0, 0.0, 0.0, 3.0, 10.0, 20.0])
    assert evaluate_context._apply(combined, 1.0, 1.0) == pytest.approx((12.0, 23.0))
    # Order matters, and the other order is a different placement.
    other = evaluate_context._mat_mul(translate, scale)
    assert other[4:] == pytest.approx([20.0, 60.0])


def embed_figure_as_pdflatex_would(figure_pdf, destination, scale, at=(100.0, 300.0)):
    """Wrap a figure PDF in one form XObject on a Letter page, then draw it scaled.

    This is the shape pdfTeX produces for ``\\includegraphics`` of a PDF: the whole
    included page becomes a form whose ``/BBox`` is its media box, placed by a
    ``cm`` transform. Building it here means the geometry reader can be checked
    against a known-exact answer without a LaTeX install.
    """
    from pypdf import PdfReader, PdfWriter, PageObject
    from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject,
                               FloatObject, NameObject, NumberObject)

    source = PdfReader(figure_pdf).pages[0]
    width = float(source.mediabox.width)
    height = float(source.mediabox.height)

    writer = PdfWriter()
    writer.add_page(PageObject.create_blank_page(width=612, height=792))
    page = writer.pages[0]

    form = DecodedStreamObject()
    form.set_data(source.get_contents().get_data())
    form.update({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Form"),
        NameObject("/FormType"): NumberObject(1),
        NameObject("/BBox"): ArrayObject(
            [FloatObject(0), FloatObject(0), FloatObject(width), FloatObject(height)]
        ),
        NameObject("/Resources"): source["/Resources"],
    })
    form_ref = writer._add_object(form)

    content = DecodedStreamObject()
    content.set_data(
        ("q %f 0 0 %f %f %f cm /Fig1 Do Q" % (scale, scale, at[0], at[1])).encode("ascii")
    )
    page[NameObject("/Contents")] = writer._add_object(content)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Fig1"): form_ref})}
    )
    writer.write(destination)
    return width, height


@pytest.mark.parametrize("scale", [1.0, 0.8218, 0.5])
def test_placed_width_is_read_out_of_the_drawing_transform(tmp_path, scale):
    """The measurement that the whole report rests on, against a known answer.

    No LaTeX needed: the figure is embedded exactly the way pdfTeX embeds one,
    at a scale chosen here, and the reader has to recover it.
    """
    figure = os.path.join(rcc.GALLERY_DIR, "line-multi", "figure.pdf")
    destination = str(tmp_path / "embedded.pdf")
    width, height = embed_figure_as_pdflatex_would(figure, destination, scale)

    from pypdf import PdfReader

    reader = PdfReader(destination)
    forms = evaluate_context.placed_forms(reader.pages[0], reader)
    assert len(forms) == 1, (
        "matplotlib's own marker glyphs are form XObjects too, but they live inside "
        "the figure's stream; only the embedded figure is at page level"
    )
    form = forms[0]
    assert form["bbox_width_pdf_pt"] == pytest.approx(width, abs=1e-6)
    assert form["placed_width_pdf_pt"] == pytest.approx(width * scale, abs=1e-6)
    assert form["placed_height_pdf_pt"] == pytest.approx(height * scale, abs=1e-6)
    assert form["placed_origin_pdf_pt"] == pytest.approx([100.0, 300.0], abs=1e-6)

    index, located, _ = evaluate_context.locate_figure_page(destination, width, height)
    assert index == 0
    assert located["placed_width_pdf_pt"] / width == pytest.approx(scale, rel=1e-9)


def test_a_figure_drawn_nowhere_is_an_error_not_a_guess(tmp_path):
    figure = os.path.join(rcc.GALLERY_DIR, "line-multi", "figure.pdf")
    destination = str(tmp_path / "embedded.pdf")
    width, height = embed_figure_as_pdflatex_would(figure, destination, 1.0)

    with pytest.raises(evaluate_context.ContextError) as excinfo:
        evaluate_context.locate_figure_page(destination, width + 50, height + 50)
    assert "not found" in str(excinfo.value)


def test_extracting_one_page_keeps_its_media_box(tmp_path):
    from pypdf import PdfReader

    figure = os.path.join(rcc.GALLERY_DIR, "line-multi", "figure.pdf")
    source = str(tmp_path / "embedded.pdf")
    embed_figure_as_pdflatex_would(figure, source, 1.0)

    reader = PdfReader(source)
    destination = str(tmp_path / "page.pdf")
    geometry = evaluate_context.extract_single_page(reader, 0, destination)

    extracted = PdfReader(destination)
    assert len(extracted.pages) == 1
    assert float(extracted.pages[0].mediabox.width) == pytest.approx(612.0, abs=1e-6)
    assert float(extracted.pages[0].mediabox.height) == pytest.approx(792.0, abs=1e-6)
    assert geometry["width_pdf_pt"] == pytest.approx(612.0)
    assert geometry["width_mm"] == pytest.approx(215.9, abs=0.05)


def test_log_diagnostics_separates_errors_from_undefined_references():
    log = (
        "./document.tex:47: Undefined control sequence.\n"
        "LaTeX Warning: Citation `foo' on page 2 undefined on input line 47.\n"
        "LaTeX Warning: Reference `bar' on page 2 undefined on input line 48.\n"
        "Overfull \\hbox (3.0pt too wide) in paragraph at lines 10--12\n"
        "LaTeX Font Info: Some harmless note on input line 3.\n"
    )
    diagnostics = evaluate_context.log_diagnostics(log)
    assert len(diagnostics["undefined_citations_or_references"]) == 2
    assert any("Citation" in line for line in diagnostics["undefined_citations_or_references"])
    assert any("Undefined control sequence" in line for line in diagnostics["errors"])
    assert len(diagnostics["bad_boxes"]) == 1
    assert evaluate_context.log_diagnostics("")["errors"] == []


def test_derived_profile_moves_the_width_and_nothing_else():
    base = figure_core.load_profile(DEFAULT_PROFILE)
    derived = evaluate_context.derive_profile(base, 69.85)

    assert derived["canvas"]["width_mm"] == pytest.approx(69.85)
    assert derived["fonts"] == base["fonts"], "type sizes must survive the width change"
    assert derived["lines"] == base["lines"]
    assert derived["colors"] == base["colors"]
    assert derived["canvas"]["aspect_ratio"] == base["canvas"]["aspect_ratio"]
    # And the repository's own profile is not touched.
    assert figure_core.load_profile(DEFAULT_PROFILE)["canvas"]["width_mm"] == base["canvas"]["width_mm"]
    assert base["canvas"]["width_mm"] != pytest.approx(69.85)


def test_derived_profile_is_marked_as_derived():
    base = figure_core.load_profile(DEFAULT_PROFILE)
    derived = evaluate_context.derive_profile(base, 82.55)
    assert derived["name"] != base["name"]
    assert "Not a new default" in derived["note"]


def test_unknown_venue_is_rejected_with_the_known_ones_listed():
    with pytest.raises(evaluate_context.ContextError) as excinfo:
        rcc.fixtures().venue("neurips2027")
    assert "neurips2027" in str(excinfo.value)
    for venue in rcc.VENUES:
        assert venue in str(excinfo.value)


def test_missing_fixture_directory_is_rejected(tmp_path):
    with pytest.raises(evaluate_context.ContextError):
        evaluate_context.Fixtures(
            conferences=str(tmp_path / "nope"),
            article=rcc.ARTICLE_DIR,
            wrappers=rcc.WRAPPERS_DIR,
        )


def test_evaluator_refuses_both_or_neither_figure_source():
    for kwargs in ({}, {"spec_path": "a.json", "figure_dir": "b"}):
        with pytest.raises(evaluate_context.ContextError) as excinfo:
            evaluate_context.evaluate(
                fixtures=rcc.fixtures(), venue_id="iclr2026", case_id="x",
                output_dir="/tmp/unused", **kwargs
            )
        assert "exactly one" in str(excinfo.value)


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

def run_generator(args):
    return subprocess.run(
        [sys.executable, os.path.join("tests", "render_conference_context.py")] + args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_generator_lists_the_matrix():
    result = run_generator(["--list"])
    assert result.returncode == 0
    for venue, case in rcc.case_ids():
        assert "%s\t%s" % (venue, case) in result.stdout


def test_generator_rejects_an_unknown_venue():
    result = run_generator(["--venue", "no-such-venue"])
    assert result.returncode == 2
    assert "no-such-venue" in result.stderr
    assert "known venues" in result.stderr


def test_generator_rejects_an_unknown_case():
    result = run_generator(["--case", "no-such-case"])
    assert result.returncode == 2
    assert "no-such-case" in result.stderr
    assert "known cases" in result.stderr


def test_generator_needs_a_selection():
    result = run_generator([])
    assert result.returncode == 2
    assert "--all" in result.stderr


def test_dependency_check_agrees_with_reality():
    result = run_generator(["--check-dependencies"])
    if HAVE_TOOLCHAIN:
        assert result.returncode == 0
        assert "toolchain present" in result.stdout
    else:
        assert result.returncode == 3
        assert "missing:" in result.stderr
        assert "apt install" in result.stderr


@pytest.mark.skipif(HAVE_TOOLCHAIN, reason="the toolchain is installed here")
def test_generator_exits_non_zero_rather_than_skipping_when_tex_is_missing():
    """Asking for the evaluation and not getting it is a failure, not a skip."""
    result = run_generator(["--all"])
    assert result.returncode == 3
    assert "did not run is not one that passed" in result.stderr


# ==========================================================================
# The committed pages
# ==========================================================================

@pytest.mark.parametrize("venue,case", rcc.case_ids())
def test_every_case_has_a_committed_page(venue, case):
    directory = rcc.case_output_dir(venue, case)
    for filename in DELIVERABLES:
        path = os.path.join(directory, filename)
        assert os.path.isfile(path), "%s missing; %s" % (path, RERUN)
        assert os.path.getsize(path) > 0


@pytest.mark.parametrize("venue,case", rcc.case_ids())
def test_committed_output_has_no_build_leftovers(venue, case):
    """The full PDF, the aux files and the logs must not have escaped the build."""
    on_disk = set(os.listdir(rcc.case_output_dir(venue, case)))
    assert on_disk == set(DELIVERABLES), (
        "%s/%s holds %s; only %s belong there"
        % (venue, case, sorted(on_disk), sorted(DELIVERABLES))
    )


@pytest.mark.parametrize("venue,case", rcc.case_ids())
def test_committed_page_is_exactly_one_page_at_the_documents_size(venue, case):
    from pypdf import PdfReader

    report = report_for(venue, case)
    reader = PdfReader(os.path.join(rcc.case_output_dir(venue, case), "page.pdf"))
    assert len(reader.pages) == 1, RERUN
    box = reader.pages[0].mediabox
    assert float(box.width) == pytest.approx(report["page"]["width_pdf_pt"], abs=0.01)
    assert float(box.height) == pytest.approx(report["page"]["height_pdf_pt"], abs=0.01)
    # US Letter, which is what all three templates set.
    assert evaluate_context.pdf_pt_to_mm(float(box.width)) == pytest.approx(215.9, abs=0.5)


@pytest.mark.parametrize("venue,case", rcc.case_ids())
def test_committed_page_is_a_body_page_not_the_title_page(venue, case):
    report = report_for(venue, case)
    assert report["page"]["pdf_page_index_zero_based"] >= 1, (
        "the figure ended up on the title page; %s" % RERUN
    )
    check = next(entry for entry in report["checks"] if entry["id"] == "page_is_body_page")
    assert check["status"] == "pass"
    assert check["detail"]["text_characters"] >= 800


@pytest.mark.parametrize("venue,case", rcc.case_ids())
def test_committed_report_has_no_failures_and_leaves_the_visual_review_open(venue, case):
    report = report_for(venue, case)
    failed = [entry["id"] for entry in report["checks"] if entry["status"] == "fail"]
    assert not failed, "%s/%s has failing checks: %s" % (venue, case, failed)

    visual = next(entry for entry in report["checks"] if entry["id"] == "visual_review")
    assert visual["status"] == "not_checked", (
        "no script may mark the visual review passed"
    )
    assert report["counts"]["not_checked"] >= 1


@pytest.mark.parametrize("venue,case", rcc.case_ids())
def test_committed_report_measured_the_width_from_the_pdf(venue, case):
    report = report_for(venue, case)
    geometry = report["geometry"]
    assert "drawing transform" in geometry["measured_from"] or "content stream" in geometry["measured_from"]
    # The drawn width really is the scale in the transform times the source width.
    assert geometry["placed_width_mm"] == pytest.approx(
        geometry["source_pdf_width_mm"] * geometry["scale"], rel=1e-4
    )
    assert geometry["drawing_matrix"][0] == pytest.approx(geometry["scale"], rel=1e-3)


@pytest.mark.parametrize("venue,case", [(v, c) for v, c in rcc.case_ids() if c in rcc.WIDTH_CASES])
def test_redrawn_cases_land_at_scale_one(venue, case):
    """The default path renders at the template's width, so nothing is shrunk."""
    report = report_for(venue, case)
    assert report["geometry"]["scale"] == pytest.approx(1.0, rel=0.005), (
        "%s/%s was placed at scale %s; the figure was supposed to be rendered at the "
        "target width" % (venue, case, report["geometry"]["scale"])
    )
    assert report["geometry"]["placed_width_mm"] == pytest.approx(
        report["geometry"]["target_width_mm"], rel=0.005
    )
    source = report["type_sizes"]["figure_source_pt"]
    effective = report["type_sizes"]["figure_effective_pt"]
    assert effective["axis_label_pt"] == pytest.approx(source["axis_label_pt"], rel=0.005)


@pytest.mark.parametrize("venue", rcc.VENUES)
def test_target_width_follows_the_venues_own_column_rule(venue):
    report = report_for(venue, "line-multi")
    template = report["template"]
    geometry = report["geometry"]
    factor = report["venue"]["target_width_factor"]

    assert geometry["target_width_mm"] == pytest.approx(
        template["float_linewidth_mm"] * factor, rel=1e-4
    )
    if report["venue"]["columns"] == 2:
        # A whole column, and narrower than half the text width would suggest.
        assert template["float_linewidth_mm"] == pytest.approx(template["columnwidth_mm"], rel=1e-4)
        assert geometry["target_width_mm"] < template["textwidth_mm"] / 2 + 5
    else:
        assert template["float_linewidth_mm"] == pytest.approx(template["textwidth_mm"], rel=1e-4)


@pytest.mark.parametrize("venue,case", [(v, c) for v, c in rcc.case_ids() if c in rcc.WIDTH_CASES])
def test_the_figures_own_checks_at_the_template_width_are_carried_through(venue, case):
    """A warning that only appears at the derived width is the point of all this.

    ``bar-signed`` fits its category labels at 85 mm and collides them at ICLR's
    69.85 mm. If the context report reduced that to a one-word status, the
    evaluation would be hiding its most useful finding.
    """
    report = report_for(venue, case)
    render_checks = report["figure_source"]["figure_checks"]
    check = next(entry for entry in report["checks"] if entry["id"] == "figure_render_checks")

    if render_checks:
        assert check["status"] in ("warn", "fail")
        for entry in render_checks:
            assert entry["id"] in check["message"]
            assert entry["message"]
    else:
        assert check["status"] == "pass"


def test_a_narrow_template_surfaces_the_bar_label_collision():
    """The concrete case: bar-signed's five categories do not fit at half width."""
    report = report_for("iclr2026", "bar-signed")
    ids = {entry["id"] for entry in report["figure_source"]["figure_checks"]}
    assert "tick_label_overlap" in ids, (
        "the category labels collide at 69.85 mm and the context report has to say so"
    )
    # And the wider ICML column does not have the same problem.
    wide = report_for("icml2026", "bar-signed")
    assert wide["template"]["float_linewidth_mm"] > report["geometry"]["target_width_mm"]


def test_the_regression_case_reports_a_real_reduction():
    """The point of this case: an 85 mm figure in a 69.85 mm slot must not be
    reported as still being 9 pt."""
    report = report_for(rcc.REGRESSION_VENUE, rcc.REGRESSION_CASE)
    geometry = report["geometry"]

    assert geometry["source_pdf_width_mm"] == pytest.approx(85.0, abs=0.3)
    assert geometry["scale"] < 0.9
    assert geometry["scale"] == pytest.approx(
        geometry["target_width_mm"] / geometry["source_pdf_width_mm"], rel=1e-3
    )

    source = report["type_sizes"]["figure_source_pt"]
    effective = report["type_sizes"]["figure_effective_pt"]
    assert effective["axis_label_pt"] < source["axis_label_pt"]
    assert effective["axis_label_pt"] == pytest.approx(
        source["axis_label_pt"] * geometry["scale"], rel=1e-3
    )

    check = next(entry for entry in report["checks"] if entry["id"] == "effective_type_size")
    assert check["status"] == "warn", "a shrunk figure must not come back a clean pass"
    assert "threshold" in check["message"], (
        "the message must say it is reporting a number, not enforcing a rule"
    )


@pytest.mark.parametrize("venue,case", rcc.case_ids())
def test_no_committed_page_claims_to_be_published(venue, case):
    """The page is the shareable artifact; the title-page disclaimer does not travel.

    Camera-ready mode is used for its layout, not for its boilerplate. ICLR's
    running head says "Published as a conference paper at ICLR 2026" and ICML
    prints an "Appearing in Proceedings" notice; neither may end up asserted on a
    page that is a typesetting fixture.
    """
    from pypdf import PdfReader

    reader = PdfReader(os.path.join(rcc.case_output_dir(venue, case), "page.pdf"))
    text = reader.pages[0].extract_text() or ""
    for claim in ("Published as a conference paper",
                  "Appearing in Proceedings",
                  "Under review as a conference paper"):
        assert claim not in text, (
            "%s/%s asserts %r on the page; %s" % (venue, case, claim, RERUN)
        )


@pytest.mark.parametrize("venue,case", rcc.case_ids())
def test_committed_report_records_units_and_provenance(venue, case):
    report = report_for(venue, case)
    assert report["template"]["measured_by"].startswith("TeX")
    assert "72.27" in report["geometry"]["units"]
    assert report["fixtures"]["body_sha256"]
    assert report["fixtures"]["wrapper_sha256"]
    assert report["environment"]["tools"]["pdflatex"]
    assert report["reproduce"]["context"].startswith("python tests/render_conference_context.py")
    assert report["venue"]["mode"] in ("finalcopy", "final", "accepted")


@pytest.mark.parametrize("venue,case", rcc.case_ids())
def test_committed_page_is_still_fresh(venue, case):
    """Templates, wrappers, body text, specs, profile and rendering code all count.

    Comparing only the default profile would not do: these pages are rendered at
    a derived width, so a change to the wrapper or the excerpt moves them just as
    surely as a change to a font size.
    """
    report = report_for(venue, case)
    recorded = report["repository"]["inputs"]
    current = rcc.fingerprint(venue, case, DEFAULT_PROFILE)["inputs"]

    stale = sorted(key for key in set(recorded) | set(current) if recorded.get(key) != current.get(key))
    assert not stale, (
        "tests/output/conference-context/%s/%s was built from a different version of: "
        "%s; %s" % (venue, case, ", ".join(stale), RERUN)
    )


def test_index_covers_the_whole_matrix():
    path = os.path.join(rcc.OUTPUT_DIR, "index.md")
    assert os.path.isfile(path), RERUN
    index = read(path)
    for venue, case in rcc.case_ids():
        assert "## %s" % rcc.fixtures().venue(venue)["name"] in index
        assert "(%s/%s/page.png)" % (venue, case) in index, (
            "%s/%s is missing from the index; %s" % (venue, case, RERUN)
        )
    assert "not printed size" in index or "do not" in index.lower()


def test_index_shows_the_measurements_actually_in_the_reports():
    index = read(os.path.join(rcc.OUTPUT_DIR, "index.md"))
    for venue, case in rcc.case_ids():
        report = report_for(venue, case)
        assert "| %.4f |" % report["geometry"]["scale"] in index, (
            "the index advertises a stale scale for %s/%s; %s" % (venue, case, RERUN)
        )


def test_index_links_resolve():
    import re

    index = read(os.path.join(rcc.OUTPUT_DIR, "index.md"))
    for _label, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", index):
        if target.startswith(("http://", "https://", "#")):
            continue
        assert os.path.exists(os.path.join(rcc.OUTPUT_DIR, target)), target


def test_index_says_the_preview_is_not_the_printed_size():
    index = read(os.path.join(rcc.OUTPUT_DIR, "index.md"))
    lowered = index.lower()
    assert "dpi" in lowered
    assert "page.pdf" in lowered
    assert "provisional" in lowered


# ==========================================================================
# Integration: actually compile
# ==========================================================================

@needs_latex
@pytest.mark.conference_context
@pytest.mark.parametrize("venue", rcc.VENUES)
def test_wrapper_compiles_on_its_own(venue, tmp_path):
    """A smoke compile of the template plus the excerpt, with no figure involved."""
    build = str(tmp_path / venue)
    os.makedirs(build)
    fixtures = rcc.fixtures()
    evaluate_context.stage_build_dir(build, fixtures, fixtures.venue(venue))
    with open(os.path.join(build, "context-figure.tex"), "w", encoding="utf-8") as handle:
        handle.write(evaluate_context.figure_block(0.5, "smoke test", placeholder=True))

    result = evaluate_context.compile_document(build, timeout=300)
    diagnostics = evaluate_context.log_diagnostics(result.log)
    assert result.ok, "%s failed to compile:\n%s" % (venue, "\n".join(diagnostics["errors"][:10]))
    assert not diagnostics["undefined_citations_or_references"], (
        "%s: %s" % (venue, diagnostics["undefined_citations_or_references"])
    )
    assert os.path.isfile(os.path.join(build, "document.pdf"))


@needs_latex
@pytest.mark.conference_context
@pytest.mark.parametrize("venue", rcc.VENUES)
def test_tex_measures_the_width_the_template_declares(venue, tmp_path):
    """The measured text width must agree with what the style file says it set.

    The manifest's `declared_textwidth` is diagnostic only — this is the test that
    would notice if a template drifted away from it.
    """
    build = str(tmp_path / venue)
    os.makedirs(build)
    fixtures = rcc.fixtures()
    entry = fixtures.venue(venue)
    evaluate_context.stage_build_dir(build, fixtures, entry)
    with open(os.path.join(build, "context-figure.tex"), "w", encoding="utf-8") as handle:
        handle.write(evaluate_context.figure_block(entry["target_width_factor"], "probe", placeholder=True))

    assert evaluate_context.compile_document(build, timeout=300).ok
    measures = evaluate_context.read_measures(build)

    textwidth_in = evaluate_context.measured_tex_pt(measures, "textwidth_tex_pt") / evaluate_context.TEX_PT_PER_INCH
    expected_in = {"iclr2026": 5.5, "neurips2026": 5.5, "icml2026": 6.75}[venue]
    assert textwidth_in == pytest.approx(expected_in, abs=0.02)

    assert int(float(measures["columns"])) == entry["columns"]
    assert float(measures["body_font_size_pt"]) > 0
    assert float(measures["caption_font_size_pt"]) > 0
    # \linewidth inside the float is the column, and in two columns that is not
    # the text width.
    float_width = evaluate_context.measured_tex_pt(measures, "float_linewidth_tex_pt")
    column_width = evaluate_context.measured_tex_pt(measures, "columnwidth_tex_pt")
    assert float_width == pytest.approx(column_width, rel=1e-4)


@needs_latex
@pytest.mark.conference_context
@pytest.mark.parametrize("venue", rcc.VENUES)
def test_end_to_end_produces_one_body_page_at_the_target_width(venue, tmp_path):
    report = evaluate_context.evaluate(
        fixtures=rcc.fixtures(),
        venue_id=venue,
        case_id="line-multi",
        output_dir=str(tmp_path / venue),
        spec_path=rcc.spec_path("line-multi"),
        png_dpi=120,
    )
    assert report["status"] != "fail", [
        entry for entry in report["checks"] if entry["status"] == "fail"
    ]
    assert report["geometry"]["scale"] == pytest.approx(1.0, rel=0.005)
    assert report["page"]["pages_in_output"] == 1
    assert report["page"]["pdf_page_index_zero_based"] >= 1
    for filename in DELIVERABLES:
        assert os.path.isfile(os.path.join(str(tmp_path / venue), filename))
    # Only the three deliverables; the build directory is gone.
    assert set(os.listdir(str(tmp_path / venue))) == set(DELIVERABLES)


@needs_latex
@pytest.mark.conference_context
def test_an_oversized_figure_is_reported_as_shrunk_not_as_unchanged(tmp_path):
    """The check that the measurement is real: place 85 mm into a half-width slot."""
    source = str(tmp_path / "figure-85mm")
    import render as render_module

    render_module.render(rcc.spec_path("line-multi"), source, DEFAULT_PROFILE)

    report = evaluate_context.evaluate(
        fixtures=rcc.fixtures(),
        venue_id="iclr2026",
        case_id="regression",
        output_dir=str(tmp_path / "out"),
        figure_dir=source,
        png_dpi=120,
    )
    scale = report["geometry"]["scale"]
    assert 0.75 < scale < 0.90
    assert report["geometry"]["source_pdf_width_mm"] == pytest.approx(85.0, abs=0.3)

    profile = figure_core.load_profile(DEFAULT_PROFILE)
    effective = report["type_sizes"]["figure_effective_pt"]
    assert effective["axis_label_pt"] == pytest.approx(
        profile["fonts"]["size_axis_label_pt"] * scale, rel=1e-3
    )
    assert effective["axis_label_pt"] < profile["fonts"]["size_axis_label_pt"] - 1.0


@needs_latex
@pytest.mark.conference_context
def test_a_figure_with_no_profile_leaves_the_type_sizes_unchecked(tmp_path):
    """Missing evidence is reported as missing, not guessed at."""
    import render as render_module

    source = str(tmp_path / "bare")
    render_module.render(rcc.spec_path("bar-signed"), source, DEFAULT_PROFILE)
    os.remove(os.path.join(source, "profile.resolved.json"))

    report = evaluate_context.evaluate(
        fixtures=rcc.fixtures(),
        venue_id="iclr2026",
        case_id="bare",
        output_dir=str(tmp_path / "out"),
        figure_dir=source,
        png_dpi=120,
    )
    check = next(entry for entry in report["checks"] if entry["id"] == "effective_type_size")
    assert check["status"] == "not_checked"
    assert "Not a pass" in check["message"]
    assert report["type_sizes"]["figure_effective_pt"] is None
    # The geometry is still measurable without the profile.
    assert report["geometry"]["placed_width_mm"] > 0


@needs_latex
@pytest.mark.conference_context
def test_a_damaged_figure_fails_with_a_message_naming_the_file(tmp_path):
    """A corrupt figure is an ordinary input, not a reason to show a stack trace."""
    source = str(tmp_path / "broken")
    os.makedirs(source)
    with open(os.path.join(source, "figure.pdf"), "wb") as handle:
        handle.write(b"%PDF-1.4\nnot actually a pdf\n")

    with pytest.raises(evaluate_context.ContextError) as excinfo:
        evaluate_context.evaluate(
            fixtures=rcc.fixtures(),
            venue_id="iclr2026",
            case_id="broken",
            output_dir=str(tmp_path / "out"),
            figure_dir=source,
        )
    message = str(excinfo.value)
    assert source in message, "the message must name the caller's directory, not a temp copy"
    assert "could not be read as a PDF" in message
    assert not os.path.isdir(str(tmp_path / "out"))


@needs_latex
@pytest.mark.conference_context
def test_the_damaged_figure_cli_exits_two_without_a_traceback(tmp_path):
    """Exit 2 and a message, not a stack trace.

    Still gated on the toolchain: a missing LaTeX is reported first (exit 3),
    because that is the more fundamental thing to tell someone.
    """
    source = str(tmp_path / "broken")
    os.makedirs(source)
    with open(os.path.join(source, "figure.pdf"), "wb") as handle:
        handle.write(b"%PDF-1.4\ntruncated\n")

    result = subprocess.run(
        [
            sys.executable,
            os.path.join(SKILL_ROOT, "scripts", "evaluate_context.py"),
            "--venue", "iclr2026", "--case", "broken",
            "--figure-dir", source,
            "--output-dir", str(tmp_path / "out"),
            "--conferences-dir", rcc.CONFERENCES_DIR,
            "--article-dir", rcc.ARTICLE_DIR,
            "--wrappers-dir", rcc.WRAPPERS_DIR,
        ],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert result.stderr.startswith("error:") or "\nerror:" in result.stderr
    assert "Traceback" not in result.stderr


@needs_latex
@pytest.mark.conference_context
def test_a_timeout_is_a_failure_not_a_silent_pass(tmp_path):
    report_dir = str(tmp_path / "out")
    with pytest.raises(evaluate_context.ContextError) as excinfo:
        evaluate_context.evaluate(
            fixtures=rcc.fixtures(),
            venue_id="iclr2026",
            case_id="timeout",
            output_dir=report_dir,
            spec_path=rcc.spec_path("line-multi"),
            timeout=0,
        )
    assert "probe" in str(excinfo.value).lower() or "timed out" in str(excinfo.value).lower()
    assert not os.path.isdir(report_dir) or "context-report.json" not in os.listdir(report_dir)


@needs_latex
@pytest.mark.conference_context
def test_the_evaluator_works_from_a_copy_of_the_skill(tmp_path):
    """A copied skill must still work, given somewhere to find the fixtures."""
    copied = str(tmp_path / "copied-skill")
    shutil.copytree(SKILL_ROOT, copied)
    output = str(tmp_path / "out")

    result = subprocess.run(
        [
            sys.executable,
            os.path.join(copied, "scripts", "evaluate_context.py"),
            "--venue", "iclr2026",
            "--case", "copied",
            "--spec", rcc.spec_path("line-multi"),
            "--output-dir", output,
            "--conferences-dir", rcc.CONFERENCES_DIR,
            "--article-dir", rcc.ARTICLE_DIR,
            "--wrappers-dir", rcc.WRAPPERS_DIR,
            "--png-dpi", "100",
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert os.path.isfile(os.path.join(output, "page.pdf"))
    report = load(os.path.join(output, "context-report.json"))
    assert report["geometry"]["scale"] == pytest.approx(1.0, rel=0.005)
