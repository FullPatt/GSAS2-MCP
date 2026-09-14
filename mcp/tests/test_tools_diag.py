"""Diagnostics, strategy and report generation."""

from __future__ import annotations

import json
import pathlib

from gsas2_mcp_server import engine, tools_data, tools_diag, tools_refine
from gsas2_mcp_server.state import get_session


# --------------------------------------------------------------------------
# auto_diagnose
# --------------------------------------------------------------------------

def test_diagnose_without_a_project() -> None:
    result = tools_diag.auto_diagnose()
    assert result["ok"] is False
    assert "No project is open" in result["error"]


def test_diagnose_an_empty_project(tmp_path, engine_ready) -> None:
    from gsas2_mcp_server import tools_project
    assert tools_project.create_project(str(tmp_path / "empty.gpx"))["ok"]

    result = tools_diag.auto_diagnose()

    assert result["ok"], result
    codes = {finding["code"] for finding in result["findings"]}
    assert "no_histograms" in codes
    assert "no_phases" in codes
    assert "not_refined" in codes
    assert result["severity"] in ("info", "warning", "error")


def test_diagnose_reports_the_missing_extension_when_relevant(project) -> None:
    result = tools_diag.auto_diagnose()
    caps = engine.capabilities()
    codes = {finding["code"] for finding in result["findings"]}

    if caps.get("refinement_available"):
        assert "engine_no_refinement" not in codes
    else:
        assert "engine_no_refinement" in codes
        finding = next(f for f in result["findings"] if f["code"] == "engine_no_refinement")
        assert finding["severity"] == "error"
        assert "pypowder" in finding["message"]
        assert result["severity"] == "error"


def test_diagnose_finds_the_unfitted_parameter_groups(project) -> None:
    result = tools_diag.auto_diagnose()
    finding = next(f for f in result["findings"] if f["code"] == "groups_not_fitted")

    # Nothing has been switched on yet, so all three groups should be listed.
    evidence = finding["evidence"]
    assert "Background" in evidence
    assert "Instrument Parameters" in evidence


def test_diagnose_notices_when_groups_are_fitted(project) -> None:
    tools_refine.set_refinement(set={"Background": True, "inst": ["U", "V", "W"]})
    result = tools_diag.auto_diagnose()

    evidence = {}
    for finding in result["findings"]:
        if finding["code"] == "groups_not_fitted":
            evidence = finding["evidence"]

    # The background is being fitted now, so it must no longer be listed.
    assert "Background" not in evidence

    # The width terms that were switched on are gone from the pending list, but
    # the ones that were not (X, Y, Z, ...) are still reported.
    pending_terms = []
    for entry in evidence.get("Instrument Parameters", []):
        pending_terms.extend(entry["terms"])
    assert "U" not in pending_terms
    assert "V" not in pending_terms
    assert "W" not in pending_terms
    assert "SH/L" in pending_terms


def test_diagnose_findings_always_carry_evidence_and_actions(project) -> None:
    result = tools_diag.auto_diagnose()
    for finding in result["findings"]:
        assert finding["code"]
        assert finding["severity"] in ("info", "warning", "error")
        assert finding["message"]
        assert "suggested_action" in finding or finding["severity"] == "info"


# --------------------------------------------------------------------------
# suggest_best_strategy
# --------------------------------------------------------------------------

def test_strategy_lists_the_standard_sequence(project) -> None:
    result = tools_diag.suggest_best_strategy()

    assert result["ok"], result
    assert len(result["steps"]) == 6
    assert [step["step"] for step in result["steps"]] == [1, 2, 3, 4, 5, 6]
    names = [step["name"] for step in result["steps"]]
    assert names[0] == "Background and scale"
    assert "Unit cell" in names
    assert names[-1] == "Atomic displacement parameters"


def test_strategy_steps_carry_executable_arguments(project) -> None:
    """Every step must be usable verbatim as a set_refinement call."""
    result = tools_diag.suggest_best_strategy()

    for step in result["steps"]:
        payload = step["set_refinement"]
        assert "set" in payload
        applied = tools_refine.set_refinement(**payload)
        assert applied["ok"], (step["name"], applied)
        # And the canonical names must survive abbreviation resolution unchanged.
        for key in payload["set"]:
            assert tools_refine._resolve_key(key) == key, key


def test_strategy_reports_whether_it_can_be_executed(project) -> None:
    result = tools_diag.suggest_best_strategy()
    caps = engine.capabilities()
    assert result["refinement_available"] == caps["refinement_available"]

    notes = " ".join(result["notes"])
    if not caps["refinement_available"]:
        assert "pypowder" in notes


def test_strategy_without_a_project() -> None:
    result = tools_diag.suggest_best_strategy()
    assert result["ok"] is False


# --------------------------------------------------------------------------
# generate_report
# --------------------------------------------------------------------------

def test_report_as_markdown(project) -> None:
    result = tools_diag.generate_report()

    assert result["ok"], result
    assert result["format"] == "markdown"
    text = result["content"]
    assert text.startswith("# GSAS-II refinement report")
    assert "## Histograms" in text
    assert "PBSO4" in text
    assert "6000" in text
    assert result["n_histograms"] == 1


def test_report_as_json_is_valid_json(project) -> None:
    result = tools_diag.generate_report(format="json")

    assert result["ok"], result
    payload = json.loads(result["content"])
    assert payload["generator"]["name"] == "GSAS2-MCP"
    assert payload["generator"]["version"]
    assert len(payload["project"]["histograms"]) == 1
    assert "capabilities" in payload
    assert payload["activity"][0]["action"] == "create_project"


def test_report_as_html(project) -> None:
    result = tools_diag.generate_report(format="html")

    assert result["ok"], result
    text = result["content"]
    assert text.startswith("<!DOCTYPE html>")
    assert "<table>" in text
    assert "<h1>GSAS-II refinement report</h1>" in text
    assert "</html>" in text
    # The Markdown pipe syntax must not survive into the HTML.
    assert "| Name | Points |" not in text


def test_report_written_to_a_file(project, tmp_path) -> None:
    target = tmp_path / "reports" / "run1.md"
    result = tools_diag.generate_report(output=str(target))

    assert result["ok"], result
    assert result["output"] == str(target.resolve())
    assert target.is_file()
    assert target.read_text(encoding="utf-8").startswith("# GSAS-II refinement report")


def test_report_includes_phases_and_atoms(project) -> None:
    assert tools_data.add_phase(phasename="PbSO4", cell=[8.48, 5.4, 6.96, 90, 90, 90])["ok"]
    phase = get_session().gpx.phase("PbSO4")
    with engine.quiet():
        phase.add_atom(0.0, 0.0, 0.0, "Pb", "Pb1")
        get_session().gpx.save()

    text = tools_diag.generate_report()["content"]

    assert "### PbSO4" in text
    assert "Pb1" in text
    assert "Space group" in text


def test_report_rejects_an_unknown_format(project) -> None:
    result = tools_diag.generate_report(format="xlsx")
    assert result["ok"] is False
    assert "Unsupported format" in result["error"]


def test_report_without_a_project() -> None:
    result = tools_diag.generate_report()
    assert result["ok"] is False


def test_report_escaping_is_safe(tmp_path, engine_ready) -> None:
    """A phase name containing markup must not break out of the HTML."""
    from gsas2_mcp_server import tools_project
    tools_project.create_project(str(tmp_path / "escape.gpx"))
    tools_data.add_phase(phasename="<script>alert(1)</script>",
                         cell=[8.48, 5.4, 6.96, 90, 90, 90])

    text = tools_diag.generate_report(format="html")["content"]

    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text
