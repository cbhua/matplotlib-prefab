"""The exported files must have the physical size the profile asks for."""

import os
import shutil
import subprocess
import sys

import pytest
from pypdf import PdfReader

import figure_core
import inspect_figure
from conftest import REPO_ROOT, SKILL_ROOT
from helpers import BAR_CASE, LINE_CASE, case, check, load_default_profile, render


@pytest.mark.parametrize("name", [LINE_CASE, BAR_CASE])
def test_pdf_page_size_matches_the_profile(tmp_path, name):
    profile = load_default_profile()
    output_dir, _ = render(tmp_path, case(name), profile=profile, subdir=name)

    page = PdfReader(os.path.join(output_dir, "figure.pdf")).pages[0]
    width_pt = float(page.mediabox.width)
    height_pt = float(page.mediabox.height)

    expected_in = figure_core.figure_size_inches(profile)
    assert width_pt == pytest.approx(expected_in[0] * 72.0, abs=0.5)
    assert height_pt == pytest.approx(expected_in[1] * 72.0, abs=0.5)
    # The headline promise: an 85 mm wide single-column figure.
    assert width_pt / 72.0 * 25.4 == pytest.approx(profile["canvas"]["width_mm"], abs=0.2)


@pytest.mark.parametrize("name", [LINE_CASE, BAR_CASE])
def test_png_pixel_size_matches_dpi(tmp_path, name):
    profile = load_default_profile()
    output_dir, report = render(tmp_path, case(name), profile=profile, subdir=name)

    size = inspect_figure.png_pixel_size(os.path.join(output_dir, "figure.png"))
    width_in, height_in = figure_core.figure_size_inches(profile)
    dpi = profile["output"]["png_dpi"]
    assert size[0] == pytest.approx(width_in * dpi, abs=1)
    assert size[1] == pytest.approx(height_in * dpi, abs=1)
    assert check(report, "png_pixel_size")["status"] == inspect_figure.PASS


def test_dpi_changes_pixels_but_not_physical_size(tmp_path):
    low = load_default_profile()
    low["output"]["png_dpi"] = 100
    high = load_default_profile()
    high["output"]["png_dpi"] = 400

    low_dir, _ = render(tmp_path, case(LINE_CASE), profile=low, subdir="low")
    high_dir, _ = render(tmp_path, case(LINE_CASE), profile=high, subdir="high")

    low_px = inspect_figure.png_pixel_size(os.path.join(low_dir, "figure.png"))
    high_px = inspect_figure.png_pixel_size(os.path.join(high_dir, "figure.png"))
    assert high_px[0] > low_px[0]

    low_pdf = PdfReader(os.path.join(low_dir, "figure.pdf")).pages[0].mediabox.width
    high_pdf = PdfReader(os.path.join(high_dir, "figure.pdf")).pages[0].mediabox.width
    assert float(low_pdf) == pytest.approx(float(high_pdf), abs=0.01)


def test_regex_page_size_agrees_with_a_real_pdf_parser(tmp_path):
    output_dir, _ = render(tmp_path, case(BAR_CASE))
    path = os.path.join(output_dir, "figure.pdf")
    scanned = inspect_figure.pdf_page_size_pt(path)
    box = PdfReader(path).pages[0].mediabox
    assert scanned[0] == pytest.approx(float(box.width), abs=0.01)
    assert scanned[1] == pytest.approx(float(box.height), abs=0.01)


def test_rendering_is_reproducible(tmp_path):
    first_dir, _ = render(tmp_path, case(LINE_CASE), subdir="a")
    second_dir, _ = render(tmp_path, case(LINE_CASE), subdir="b")
    # Byte equality is not promised (PDFs carry timestamps); the drawing is.
    with open(os.path.join(first_dir, "figure.png"), "rb") as handle:
        first_png = handle.read()
    with open(os.path.join(second_dir, "figure.png"), "rb") as handle:
        second_png = handle.read()
    assert first_png == second_png

    for name in ("spec.json", "profile.resolved.json"):
        with open(os.path.join(first_dir, name), encoding="utf-8") as handle:
            first = handle.read()
        with open(os.path.join(second_dir, name), encoding="utf-8") as handle:
            assert handle.read() == first


# --------------------------------------------------------------------------
# CLI and portability
# --------------------------------------------------------------------------

def run_cli(args, cwd):
    return subprocess.run(
        [sys.executable] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("name", [LINE_CASE, BAR_CASE])
def test_documented_command_works_from_the_repository_root(tmp_path, name):
    output_dir = os.path.join(str(tmp_path), name)
    result = run_cli(
        [
            os.path.join("skills", "scientific-figures", "scripts", "render.py"),
            "--spec",
            os.path.join("tests", "data", "%s.json" % name),
            "--output-dir",
            output_dir,
        ],
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "status:" in result.stdout
    for filename in ("figure.pdf", "figure.png", "report.json"):
        assert os.path.isfile(os.path.join(output_dir, filename))


def test_invalid_spec_exits_with_an_error_not_a_traceback(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version": "1", "kind": "pie", "x_label": "a", "y_label": "b"}')
    result = run_cli(
        [
            os.path.join("skills", "scientific-figures", "scripts", "render.py"),
            "--spec",
            str(bad),
            "--output-dir",
            str(tmp_path / "out"),
        ],
        cwd=REPO_ROOT,
    )
    assert result.returncode == 2
    assert result.stderr.startswith("error:")
    assert "pie" in result.stderr
    assert "Traceback" not in result.stderr


def test_skill_directory_is_self_contained(tmp_path):
    """Copy the skill somewhere else, run it from an unrelated cwd, with an external spec."""
    copied = os.path.join(str(tmp_path), "copied-skill")
    shutil.copytree(SKILL_ROOT, copied)

    spec_path = os.path.join(str(tmp_path), "external-spec.json")
    shutil.copyfile(case(BAR_CASE), spec_path)

    elsewhere = os.path.join(str(tmp_path), "elsewhere")
    os.makedirs(elsewhere)
    output_dir = os.path.join(str(tmp_path), "copied-out")

    result = run_cli(
        [
            os.path.join(copied, "scripts", "render.py"),
            "--spec",
            spec_path,
            "--output-dir",
            output_dir,
        ],
        cwd=elsewhere,
    )
    assert result.returncode == 0, result.stderr
    assert os.path.isfile(os.path.join(output_dir, "figure.pdf"))
    assert os.path.isfile(os.path.join(output_dir, "figure.png"))


def test_inspect_cli_rechecks_an_existing_output_directory(tmp_path):
    output_dir, _ = render(tmp_path, case(LINE_CASE))
    result = run_cli(
        [os.path.join(SKILL_ROOT, "scripts", "inspect_figure.py"), "--output-dir", output_dir],
        cwd=str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    import json

    payload = json.loads(result.stdout)
    assert payload["status"] != inspect_figure.FAIL
    assert payload["mode"] == "output-dir-only"
    ids = {entry["id"] for entry in payload["checks"]}
    assert {"outputs_present", "png_pixel_size", "pdf_page_size", "visual_review"} <= ids


def test_inspect_cli_reports_a_truncated_export(tmp_path):
    output_dir, _ = render(tmp_path, case(LINE_CASE))
    with open(os.path.join(output_dir, "figure.png"), "wb"):
        pass  # truncate to zero bytes
    result = run_cli(
        [os.path.join(SKILL_ROOT, "scripts", "inspect_figure.py"), "--output-dir", output_dir],
        cwd=str(tmp_path),
    )
    assert result.returncode == 1
    assert "figure.png" in result.stdout
