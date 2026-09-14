"""Data import tools: powder patterns, phases, images, and file inspection.

Everything here is expected to work on a plain GSAS-II source checkout with or
without the compiled Fortran extensions -- except CIF phase import, which needs
``pyspg`` for the space-group tables and is asserted accordingly.
"""

from __future__ import annotations

import pathlib

import pytest

from gsas2_mcp_server import engine, tools_data, tools_project
from gsas2_mcp_server.state import get_session

PB_SO4_CELL = [8.48, 5.40, 6.96, 90.0, 90.0, 90.0]


# --------------------------------------------------------------------------
# add_powder_histogram
# --------------------------------------------------------------------------

def test_add_powder_histogram(tmp_path, engine_ready, testinp) -> None:
    assert tools_project.create_project(str(tmp_path / "p.gpx"))["ok"]

    result = tools_data.add_powder_histogram(
        str(testinp / "PBSO4.XRA"), iparams=str(testinp / "INST_XRY.PRM"))

    assert result["ok"], result
    hist = result["histogram"]
    assert hist["name"].startswith("PWDR")
    assert hist["n_points"] == 6000, "PBSO4.XRA holds 6000 points"
    assert result["n_histograms"] == 1
    assert get_session().open


def test_add_powder_histogram_reports_a_missing_file(tmp_path, engine_ready) -> None:
    assert tools_project.create_project(str(tmp_path / "p.gpx"))["ok"]

    result = tools_data.add_powder_histogram(str(tmp_path / "absent.xra"))

    assert result["ok"] is False
    assert "No such data file" in result["error"]


def test_add_powder_histogram_reports_a_missing_instrument_file(tmp_path, engine_ready, testinp) -> None:
    assert tools_project.create_project(str(tmp_path / "p.gpx"))["ok"]

    result = tools_data.add_powder_histogram(
        str(testinp / "PBSO4.XRA"), iparams=str(tmp_path / "absent.prm"))

    assert result["ok"] is False
    assert "instrument parameter file" in result["error"]


def test_add_powder_histogram_needs_a_project(engine_ready, testinp) -> None:
    result = tools_data.add_powder_histogram(str(testinp / "PBSO4.XRA"))
    assert result["ok"] is False
    assert "No project is open" in result["error"]


def test_fmthint_restricts_the_importer(tmp_path, engine_ready, testinp) -> None:
    assert tools_project.create_project(str(tmp_path / "p.gpx"))["ok"]

    good = tools_data.add_powder_histogram(
        str(testinp / "PBSO4.XRA"), iparams=str(testinp / "INST_XRY.PRM"),
        fmthint="GSAS")
    assert good["ok"], good

    # A format name that cannot match must fail rather than silently guessing.
    bad = tools_data.add_powder_histogram(
        str(testinp / "PBSO4.XRA"), iparams=str(testinp / "INST_XRY.PRM"),
        fmthint="no-such-format-xyz")
    assert bad["ok"] is False


# --------------------------------------------------------------------------
# add_phase
# --------------------------------------------------------------------------

def test_add_phase_from_scratch(project) -> None:
    """Building a P 1 phase needs no space-group tables, so it always works."""
    result = tools_data.add_phase(phasename="PbSO4-P1", spacegroup="P 1",
                                  cell=PB_SO4_CELL, histograms=["all"])

    assert result["ok"], result
    phase = result["phase"]
    assert phase["name"] == "PbSO4-P1"
    assert phase["space_group"] == "P 1"
    assert phase["cell"]["length_a"] == pytest.approx(8.48)
    assert phase["cell"]["length_c"] == pytest.approx(6.96)
    assert phase["n_atoms"] == 0
    assert result["n_phases"] == 1


def test_add_phase_from_a_cif(project, testinp) -> None:
    """CIF import works when pyspg is present, and fails cleanly when it is not."""
    result = tools_data.add_phase(str(testinp / "PbSO4-Wyckoff.cif"),
                                  histograms=["all"])
    caps = engine.capabilities()

    if caps.get("spacegroup_tables_available"):
        assert result["ok"], result
        assert result["phase"]["n_atoms"] > 0
        assert result["phase"]["space_group"]
    else:
        assert result["ok"] is False
        assert "pyspg" in result["hint"]
        assert result["error"]


def test_add_phase_requires_a_name_or_a_file(project) -> None:
    result = tools_data.add_phase()
    assert result["ok"] is False
    assert "phasefile" in result["error"]


def test_add_phase_validates_the_cell(project) -> None:
    result = tools_data.add_phase(phasename="bad", cell=[1.0, 2.0, 3.0])
    assert result["ok"] is False
    assert "six values" in result["error"]


def test_add_phase_reports_a_missing_file(project, tmp_path) -> None:
    result = tools_data.add_phase(str(tmp_path / "nope.cif"))
    assert result["ok"] is False
    assert "No such phase file" in result["error"]


def test_add_phase_reports_an_unknown_histogram(project) -> None:
    """A mistyped histogram name is caught here, not inside GSAS-II.

    GSAS-II builds a broken phase when the name does not resolve and then fails
    with "'NoneType' object has no attribute 'name'", which tells an agent
    nothing.  The tool must name the offending argument and list the real ones.
    """
    result = tools_data.add_phase(phasename="PbSO4", spacegroup="P 1",
                                  cell=PB_SO4_CELL,
                                  histograms=["PWDR NOPE.XRA"])

    assert result["ok"] is False
    assert "PWDR NOPE.XRA" in result["error"]
    available = result["available_histograms"]
    assert available, "the real histogram names must be offered back"
    assert available[0] in result["hint"]
    assert "NoneType" not in result["error"]


def test_add_phase_links_every_histogram_by_default(project) -> None:
    """Omitting histograms links the phase to the project's data."""
    result = tools_data.add_phase(phasename="PbSO4-default", cell=PB_SO4_CELL)

    assert result["ok"], result
    assert result["linked_histograms"] == ["PWDR PBSO4.XRA Bank 1"]
    assert result["phase"]["histograms"] == ["PWDR PBSO4.XRA Bank 1"]


def test_phase_can_be_added_and_atoms_appended(project) -> None:
    """A phase built from scratch is editable through the GSAS-II objects."""
    added = tools_data.add_phase(phasename="Editable", cell=PB_SO4_CELL)
    assert added["ok"], added

    phase = get_session().gpx.phase("Editable")
    with engine.quiet():
        phase.add_atom(0.0, 0.0, 0.0, "Pb", "Pb1")
        phase.add_atom(0.25, 0.25, 0.25, "S", "S1", occ=1.0, uiso=0.01)
        get_session().gpx.save()

    summary = tools_project.project_summary()
    entry = next(p for p in summary["phases"] if p["name"] == "Editable")
    assert entry["n_atoms"] == 2
    assert [a["label"] for a in entry["atoms"]] == ["Pb1", "S1"]
    assert entry["atoms"][0]["element"] == "Pb"


# --------------------------------------------------------------------------
# add_image
# --------------------------------------------------------------------------

def test_add_image_accepts_a_baseline_tiff(project, tiff_image) -> None:
    result = tools_data.add_image(str(tiff_image))

    if not result["ok"]:
        # Some builds ship without image support; that must still be structured.
        assert result["error"]
        assert "hint" in result
        pytest.skip("image import unavailable in this build: {}".format(result["error"]))

    assert result["images"], result
    assert result["n_images"] >= 1
    assert all(name.startswith("IMG") for name in result["images"])


def test_add_image_reports_a_missing_file(project, tmp_path) -> None:
    result = tools_data.add_image(str(tmp_path / "nope.tif"))
    assert result["ok"] is False
    assert "No such image file" in result["error"]


# --------------------------------------------------------------------------
# load_data
# --------------------------------------------------------------------------

def test_load_data_summarises_a_pattern_without_touching_the_project(
        tmp_path, engine_ready, testinp) -> None:
    assert tools_project.create_project(str(tmp_path / "p.gpx"))["ok"]

    result = tools_data.load_data(str(testinp / "PBSO4.XRA"))

    assert result["ok"], result
    assert result["reader_kind"] == "Pwdr"
    assert result["n_banks"] == 1
    bank = result["banks"][0]
    assert bank["n_points"] == 6000
    assert bank["x_min"] == pytest.approx(10.0, abs=0.01)
    assert bank["x_max"] == pytest.approx(159.975, abs=0.01)
    assert bank["n_columns"] == 6

    # Nothing was added to the project.
    assert tools_project.project_summary()["histograms"] == []


def test_load_data_can_be_called_with_no_project_open(engine_ready, testinp) -> None:
    result = tools_data.load_data(str(testinp / "PBSO4.XRA"))
    assert result["ok"], result


def test_load_data_reports_a_missing_file(tmp_path, engine_ready) -> None:
    result = tools_data.load_data(str(tmp_path / "absent.xra"))
    assert result["ok"] is False
    assert "No such file" in result["error"]


def test_load_data_rejects_unreadable_content(tmp_path, engine_ready) -> None:
    junk = tmp_path / "junk.xra"
    junk.write_text("not a diffraction pattern at all\n")
    result = tools_data.load_data(str(junk))
    assert result["ok"] is False


def test_load_data_guesses_the_reader_from_the_extension(engine_ready, testinp) -> None:
    cif = tools_data.load_data(str(testinp / "PbSO4-Wyckoff.cif"))
    # Either the CIF was read, or it failed cleanly for the documented reason.
    if cif["ok"]:
        assert cif["reader_kind"] == "Phase"
    else:
        assert cif["error"]
    assert tools_data._guess_reader_kind("x.cif") == "Phase"
    assert tools_data._guess_reader_kind("x.tif") == "Image"
    assert tools_data._guess_reader_kind("x.xra") == "Pwdr"
    assert tools_data._guess_reader_kind("x.hkl") == "HKLF"
