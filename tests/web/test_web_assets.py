"""The published assets are copies of this repository, and they are current.

A site built from a stale copy of ``figure_core.py`` would draw with different
code from the command line while claiming to draw with the same. These tests are
what makes that a failure rather than a surprise.
"""

from __future__ import annotations

import json
import os

import pytest

import build_web_assets
import fetch_pyodide
from conftest import GENERATED, REPO_ROOT, needs_runtime


def test_every_generated_python_file_matches_its_source():
    stale = []
    for record in build_web_assets.entries():
        target = os.path.join(GENERATED, record["target"])
        assert os.path.isfile(target), (
            "%s has not been generated; run `python scripts/build_web_assets.py`"
            % record["target"]
        )
        if build_web_assets.sha256_file(target) != record["sha256"]:
            stale.append(record["target"])
    assert not stale, (
        "these published copies no longer match the repository: %s; run "
        "`python scripts/build_web_assets.py`" % ", ".join(stale)
    )


def test_the_manifest_records_the_digests_it_copied():
    with open(os.path.join(GENERATED, "assets-manifest.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)
    assert manifest["files"] == build_web_assets.entries(), (
        "assets-manifest.json is out of date; run `python scripts/build_web_assets.py`"
    )


def test_the_worker_loads_the_shared_module_not_a_copy_of_its_own():
    """The published figure_core is the skill's, byte for byte."""
    published = os.path.join(GENERATED, "python", "skill", "scripts", "figure_core.py")
    source = os.path.join(REPO_ROOT, "skills", "scientific-figures", "scripts", "figure_core.py")
    with open(published, "rb") as a, open(source, "rb") as b:
        assert a.read() == b.read()


def test_the_pyodide_lock_pins_exact_versions():
    lock = fetch_pyodide.load_lock()
    assert lock["pyodide_version"], "the lock file must name a version"
    assert "latest" not in lock["base_url"], "the runtime must not be pinned to a moving target"
    for entry in lock["files"]:
        assert len(entry["sha256"]) == 64
        assert entry["bytes"] > 0
    for name in ("matplotlib", "numpy"):
        assert name in lock["packages"], "%s must be pinned" % name


@needs_runtime
def test_the_fetched_runtime_matches_the_lock():
    lock = fetch_pyodide.load_lock()
    wrong = []
    for entry in lock["files"]:
        path = os.path.join(GENERATED, "pyodide", entry["name"])
        if fetch_pyodide.sha256_file(path) != entry["sha256"]:
            wrong.append(entry["name"])
    assert not wrong, "these runtime files do not match the lock: %s" % ", ".join(wrong)


def test_packaged_fonts_were_verified_against_the_compiled_pages():
    path = os.path.join(GENERATED, "fonts", "fonts.json")
    if not os.path.isfile(path):
        pytest.skip("fonts are not packaged; run `python scripts/build_fonts.py`")
    with open(path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    verification = manifest.get("verification")
    assert verification, (
        "the font manifest carries no verification, so nothing shows these are the faces "
        "the venue PDFs use; run `python scripts/build_fonts.py`"
    )
    checked = [entry for entry in verification if entry.get("checked")]
    assert checked, "no font in any compiled page was checked against a packaged face"
    for entry in checked:
        assert not entry["mismatches"], (
            "%s in %s has advance widths that differ from the packaged face: %s"
            % (entry["font"], entry["pdf"], entry["mismatches"][:3])
        )
        assert not entry["glyphs_missing_from_packaged_face"], (
            "%s in %s uses glyphs the packaged face does not have: %s"
            % (entry["font"], entry["pdf"], entry["glyphs_missing_from_packaged_face"][:5])
        )


def test_the_licence_travels_with_the_fonts():
    directory = os.path.join(GENERATED, "fonts")
    if not os.path.isdir(directory):
        pytest.skip("fonts are not packaged")
    assert os.path.isfile(os.path.join(directory, "LICENCE-urw-base35.txt")), (
        "redistributed fonts must carry their licence"
    )
