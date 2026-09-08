"""The committed verification evidence passed, and describes the code that is here.

Every expensive check in this project writes a report and commits it. These
tests do two things with those reports: assert they passed, and assert they were
produced from the files currently in the repository. Without the second, a
report is only a record of something that was once true.
"""

from __future__ import annotations

import pytest

import web_fingerprint
from conftest import load_report

REPORTS = [
    ("page-calibration.json",),
    ("render-equivalence.json",),
    ("export-roundtrip.json",),
    ("end-to-end", "end-to-end.json"),
]


@pytest.mark.parametrize("parts", REPORTS, ids=[p[-1] for p in REPORTS])
def test_the_report_passed(parts):
    report = load_report(*parts)
    status = report.get("status")
    if status is None:  # page-calibration lists per-page status instead
        assert all(entry["status"] == "pass" for entry in report["pages"])
        return
    assert status == "pass", report.get("cases") or report


@pytest.mark.parametrize("parts", REPORTS, ids=[p[-1] for p in REPORTS])
def test_the_report_describes_the_code_that_is_here(parts):
    report = load_report(*parts)
    recorded = report.get("repository", {}).get("inputs")
    assert recorded, "%s carries no fingerprint, so it cannot be shown to be current" % parts[-1]
    stale = web_fingerprint.stale(recorded)
    assert not stale, (
        "%s was produced from a different version of: %s; %s"
        % (parts[-1], ", ".join(stale), web_fingerprint.RERUN)
    )


def test_the_prototype_gate_was_met():
    """Phase A's question: does the repository's code run in a browser at all?"""
    report = load_report("pyodide-prototype.json")
    assert report["status"] == "pass"
    failed = [check["id"] for check in report["checks"] if not check["passed"]]
    assert not failed, failed
    assert report["svg_equivalence"]["against_parity_venv"]["identical"]


def test_every_equivalence_case_is_byte_identical():
    report = load_report("render-equivalence.json")
    assert len(report["cases"]) >= 10, "the matrix must cover more than the defaults"
    for case in report["cases"]:
        assert case["status"] == "pass", case
        assert case["comparison"]["identical"], case["id"]
    kinds = {case["spec"].split("-")[0] for case in report["cases"]}
    assert kinds == {"line", "bar"}, "both chart kinds must be in the matrix"
    venues = {case["venue"] for case in report["cases"]}
    assert len(venues) == 3, "every venue must be in the matrix"


def test_the_interaction_latency_target_was_measured_not_assumed():
    report = load_report("render-equivalence.json")
    latency = report["latency"]
    assert latency["samples"] >= 30, (
        "the target is stated over at least thirty measurements; this run has %d"
        % latency["samples"]
    )
    assert latency["meets_target"], (
        "p95 was %s ms against a %s ms target" % (latency["p95_ms"], latency["target_p95_ms"])
    )


def test_the_end_to_end_matrix_covers_twelve_default_pages_and_tuned_cases():
    report = load_report("end-to-end", "end-to-end.json")
    defaults = [case for case in report["cases"] if case["id"].startswith("default-")]
    assert len(defaults) == 12, (
        "three venues x two width modes x two chart kinds is twelve pages; found %d"
        % len(defaults)
    )
    tuned = [case for case in report["cases"] if case["id"].startswith("tuned-")]
    assert {case["venue"] for case in tuned} == {"iclr2026", "neurips2026", "icml2026"}, (
        "each venue needs at least one deliberately edited case"
    )
    for case in report["cases"]:
        assert case["status"] == "pass", case["id"]
        assert case["figure"]["scale"] == pytest.approx(1.0, abs=0.005), (
            "%s was scaled on the page; the figure must be inserted at its own size"
            % case["id"]
        )


def test_browser_coverage_is_stated_rather_than_implied():
    report = load_report("browsers.json")
    assert "chromium" in report["engines_tested"], (
        "the calibration baseline engine must be among the tested ones"
    )
    for entry in report["engines"]:
        if entry["tested"]:
            assert entry["status"] == "pass", entry["engine"]
        else:
            assert entry.get("reason_not_tested"), (
                "an untested engine must say why, so it is not read as passing"
            )
    assert report["coverage_claim"]


def test_the_parity_environment_matched_the_browser():
    report = load_report("render-equivalence.json")
    local = report["local_environment"]
    assert local["matches"], (
        "the local comparison interpreter did not match the browser's versions, so the "
        "equivalence result would not mean what it says"
    )
    assert local["browser_versions"]["matplotlib"] == local["installed"]["matplotlib"]
    assert local["browser_versions"]["numpy"] == local["installed"]["numpy"]
    # And the residual difference is stated rather than hidden.
    assert local["python_difference_note"]
