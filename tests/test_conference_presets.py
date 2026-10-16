"""Venue references must survive copying and preserve scientific/render contracts."""

import copy
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import conference_presets
import figure_core
import inspect_figure
import render
from conftest import SKILL_ROOT
from helpers import BAR_SPEC, LINE_SPEC


def reference_checks(spec=None, edit=None, wrap=None):
    preset, profile, _ = conference_presets.load_preset("iclr2026-first", SKILL_ROOT)
    if edit:
        for section, values in edit.items():
            profile[section].update(values)
    report = conference_presets.evaluate_preset(spec or LINE_SPEC, profile, preset, wrap)
    return {item["id"]: item for item in report.checks}


@pytest.mark.parametrize("size,status", [(8.49, "warn"), (8.5, "pass"), (9, "pass"), (9.5, "pass"), (9.51, "warn"), (10, "warn")])
def test_body_relative_axis_boundaries(size, status):
    checks = reference_checks(edit={"fonts": {"size_axis_label_pt": size}})
    assert checks["reference.x_label"]["status"] == status
    assert checks["reference.y_label"]["details"]["body_ratio"] == pytest.approx(size / 10)


def test_per_axis_overrides_consistency_and_effective_tick_intersection():
    checks = reference_checks(edit={"fonts": {"size_x_label_pt": 8.5, "size_y_label_pt": 9}})
    assert checks["reference.axis_label_consistency"]["status"] == "warn"
    assert checks["reference.xtick"]["status"] == "warn"
    assert checks["reference.xtick"]["details"]["maximum_pt"] == pytest.approx(7.8)
    assert checks["reference.ytick"]["status"] == "pass"


def test_impossible_tick_intersection_is_deferred_not_recommended():
    checks = reference_checks(edit={"fonts": {"size_x_label_pt": 3}})
    assert checks["reference.x_label"]["status"] == "warn"
    tick = checks["reference.xtick"]
    assert tick["status"] == "pass"
    assert tick["details"]["axis_relative_constraint_deferred"]
    assert tick["details"]["minimum_pt"] == 7.5
    assert tick["details"]["maximum_pt"] == 8


def test_absent_roles_do_not_warn_and_shared_grid_issues_are_grouped():
    bare = copy.deepcopy(BAR_SPEC)
    bare.update(x_label="", y_label="")
    checks = reference_checks(bare, {"fonts": {"size_axis_label_pt": 20, "size_legend_pt": 20}})
    assert "reference.x_label" not in checks
    assert "reference.legend" not in checks
    assert "reference.axis_label_consistency" not in checks
    assert checks["reference.xtick"]["status"] == "pass"
    grid = {"kind": "grid", "rows": 1, "columns": 2, "panels": [LINE_SPEC, bare]}
    checks = reference_checks(grid, {"fonts": {"size_axis_label_pt": 20}})
    assert checks["reference.x_label"]["details"]["panel_indices"] == [0]
    assert checks["reference.xtick"]["details"]["axis_relative_constraint_deferred"]


@pytest.mark.parametrize("ratio,status,cramped", [(0.24, "warn", True), (0.25, "warn", False), (1/3, "pass", False), (0.5, "pass", False), (2/3, "pass", False), (0.7, "warn", False)])
def test_wrapped_width_uses_body_not_paper_width(ratio, status, cramped):
    check = reference_checks(edit={"canvas": {"width_mm": 139.7 * ratio}})["reference.wrapped_figure_width"]
    assert check["status"] == status
    assert check["details"]["caption_cramped"] is cramped


def test_full_width_nonwrapped_is_exempt_and_evaluation_does_not_mutate_data():
    before = copy.deepcopy(LINE_SPEC)
    checks = reference_checks(LINE_SPEC, {"canvas": {"width_mm": 139.7}}, wrap=False)
    assert "reference.wrapped_figure_width" not in checks
    assert checks["reference.text_width"]["status"] == "pass"
    assert LINE_SPEC == before


def test_legends_and_thin_strokes_warn_without_inventing_heavy_stroke_limit():
    spec = copy.deepcopy(LINE_SPEC)
    spec["series"].append({"name": "b", "y": [2, 3, 4, 5]})
    checks = reference_checks(spec, {"fonts": {"size_legend_pt": 11}, "lines": {"data_linewidth_pt": 0.1}})
    assert checks["reference.legend"]["status"] == "warn"
    assert checks["reference.strokes"]["details"]["below_floor"] == {"data": 0.1}
    assert reference_checks(edit={"lines": {"data_linewidth_pt": 5}})["reference.strokes"]["status"] == "pass"


def test_reference_typography_scales_with_body_context():
    preset, profile, _ = conference_presets.load_preset("iclr2026-first", SKILL_ROOT)
    preset["paper"]["body_size_pt"] = 12
    profile["fonts"].update(size_axis_label_pt=10.8, size_tick_pt=9.6)
    checks = conference_presets.evaluate_preset(LINE_SPEC, profile, preset).checks
    assert next(c for c in checks if c["id"] == "reference.x_label")["status"] == "pass"
    assert next(c for c in checks if c["id"] == "reference.xtick")["status"] == "pass"


def test_portable_skill_renders_exact_iclr_size_and_reproduces(tmp_path):
    skill = tmp_path / "copied skill"
    shutil.copytree(SKILL_ROOT, skill, ignore=shutil.ignore_patterns("__pycache__"))
    output = tmp_path / "paper figures"
    command = [sys.executable, str(skill / "scripts/render.py"), "--preset", "iclr2026-first",
               "--spec", str(skill / "assets/examples/line.json"), "--output-dir", str(output)]
    completed = subprocess.run(command, cwd=tmp_path, text=True, capture_output=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert {p.name for p in output.iterdir()} == {"figure.pdf", "figure.png", "spec.json", "profile.resolved.json", "report.json"}
    width, height = inspect_figure.pdf_page_size_pt(str(output / "figure.pdf"))
    assert width * 25.4 / 72 == pytest.approx(69.85)
    assert height * 25.4 / 72 == pytest.approx(43.1673)
    profile = json.loads((output / "profile.resolved.json").read_text())
    assert figure_core.font_size(profile, "x_label") == 9
    assert figure_core.font_size(profile, "xtick") == 8
    report = json.loads((output / "report.json").read_text())
    assert report["counts"]["fail"] == report["counts"]["warn"] == 0
    assert report["counts"]["not_checked"] == 4
    assert not report["conference_reference"]["article_placement_verified"]
    assert report["conference_reference"]["preset"]["id"] == "iclr2026-first"
    assert json.loads((output / "spec.json").read_text())["series"] == json.loads((skill / "assets/examples/line.json").read_text())["series"]
    (output / "notes.txt").write_text("keep me")
    reproduce = shlex.split(report["reproduce"])
    reproduce[0] = sys.executable
    repeated = subprocess.run(reproduce, cwd=tmp_path, text=True, capture_output=True)
    assert repeated.returncode == 0, repeated.stdout + repeated.stderr
    assert json.loads((output / "profile.resolved.json").read_text()) == profile
    assert (output / "notes.txt").read_text() == "keep me"


def test_explicit_profile_retains_styles_with_reference_warnings(tmp_path):
    preset, profile, _ = conference_presets.load_preset("iclr2026-first", SKILL_ROOT)
    profile["fonts"]["size_x_label_pt"] = 11
    profile["canvas"]["width_mm"] = 139.7
    profile_path = tmp_path / "chosen.json"
    profile_path.write_text(json.dumps(profile))
    spec = Path(SKILL_ROOT) / "assets/examples/line.json"
    report = render.render(str(spec), str(tmp_path / "out"), str(profile_path), preset["id"], False)
    resolved = json.loads((tmp_path / "out/profile.resolved.json").read_text())
    assert resolved["fonts"]["size_x_label_pt"] == 11
    checks = {c["id"]: c for c in report["checks"]}
    assert checks["reference.x_label"]["status"] == "warn"
    assert "reference.wrapped_figure_width" not in checks
    assert report["counts"]["warn"] > 0 and report["status"] == "warn"
    assert "--text-wrap off" in report["reproduce"]


@pytest.mark.parametrize("preset_id", ["not-a-venue", "../single-column", "/tmp/preset"])
def test_unknown_or_path_preset_fails_before_output(tmp_path, preset_id):
    with pytest.raises(figure_core.ProfileError):
        render.render(str(Path(SKILL_ROOT) / "assets/examples/line.json"), str(tmp_path / "out"), preset=preset_id)
    assert not (tmp_path / "out").exists()
