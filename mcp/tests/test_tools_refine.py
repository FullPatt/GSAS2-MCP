"""Refinement control: flags, the fit itself, holds, and results.

On a build without the compiled extensions the fit itself cannot run.  The
tests assert either a successful refinement or the documented structured
error -- never an unhandled exception.
"""

from __future__ import annotations

import pytest

from gsas2_mcp_server import engine, tools_refine
from gsas2_mcp_server.state import get_session


# --------------------------------------------------------------------------
# abbreviation handling
# --------------------------------------------------------------------------

@pytest.mark.parametrize("given,expected", [
    ("bg", "Background"),
    ("bkg", "Background"),
    ("BACKGROUND", "Background"),
    ("background", "Background"),
    ("inst", "Instrument Parameters"),
    ("instr", "Instrument Parameters"),
    ("instrument_parameters", "Instrument Parameters"),
    ("lattice", "Cell"),
    ("cell", "Cell"),
    ("unit-cell", "Cell"),
    ("strain", "Mustrain"),
    ("mustrain", "Mustrain"),
    ("texture", "Pref.Ori."),
    ("pref.ori", "Pref.Ori."),
    ("phasefraction", "PhaseFraction"),
    ("scale", "Scale"),
    ("coords", "Atoms"),
    ("size", "Size"),
    ("hstrain", "HStrain"),
    ("lebail", "LeBail"),
])
def test_abbreviations_resolve_to_canonical_names(given: str, expected: str) -> None:
    assert tools_refine._resolve_key(given) == expected


def test_unknown_keys_are_passed_through_for_gsas_ii_to_reject() -> None:
    """Invented names are not silently dropped; GSAS-II reports them."""
    assert tools_refine._resolve_key("definitely-not-a-parameter") == \
        "definitely-not-a-parameter"


def test_resolve_mapping_reports_the_renames() -> None:
    resolved, renames = tools_refine._resolve_mapping({"bg": True, "lattice": True,
                                                       "Scale": True})
    assert resolved == {"Background": True, "Cell": True, "Scale": True}
    assert renames == {"bg": "Background", "lattice": "Cell"}
    assert tools_refine._resolve_mapping(None) == ({}, {})


def test_abbreviation_table_only_maps_to_real_parameters() -> None:
    """Every abbreviation target must be a name GSAS-II actually accepts."""
    allowed = set(tools_refine.HISTOGRAM_KEYS) | set(tools_refine.PHASE_KEYS) | \
        set(tools_refine.HAP_KEYS)
    for shorthand, canonical in tools_refine.ABBREVIATIONS.items():
        assert canonical in allowed, (shorthand, canonical)


# --------------------------------------------------------------------------
# set_refinement
# --------------------------------------------------------------------------

def test_set_refinement_accepts_abbreviations(project) -> None:
    result = tools_refine.set_refinement(set={"bg": True, "scale": True})

    assert result["ok"], result
    assert result["applied"]["set"] == {"Background": True, "Scale": True}
    assert result["renamed"] == {"bg": "Background", "scale": "Scale"}

    flags = result["project"]["histograms"][0]
    assert flags["background"] is True


def test_set_refinement_background_dictionary_form(project) -> None:
    result = tools_refine.set_refinement(
        set={"Background": {"type": "chebyschev-1", "no. coeffs": 8, "refine": True}})

    assert result["ok"], result
    hist = get_session().gpx.histograms()[0]
    background_type, refine_flag = hist.data["Background"][0][:2]
    assert background_type == "chebyschev-1"
    assert refine_flag is True
    # Background is [type, refine, n_coeffs, *coeffs].
    assert hist.data["Background"][0][2] == 8
    assert len(hist.data["Background"][0]) - 3 == 8


def test_set_refinement_instrument_parameters(project) -> None:
    result = tools_refine.set_refinement(set={"inst": ["U", "V", "W"]})
    assert result["ok"], result

    hist = get_session().gpx.histograms()[0]
    instrument = hist.data["Instrument Parameters"][0]
    for term in ("U", "V", "W"):
        assert instrument[term][2], term


def test_background_flag_does_not_swallow_other_histogram_keys(project) -> None:
    """Regression test for a GSAS-II early-return that dropped sibling keys.

    ``G2PwdrData.set_refinements`` used to ``return`` as soon as it saw a plain
    boolean ``Background``, so ``{'Background': True, 'Instrument Parameters':
    [...]}`` in one call quietly enabled only the background.  The fork changes
    that to ``continue``; this test pins the behaviour.
    """
    result = tools_refine.set_refinement(
        set={"Background": True, "Instrument Parameters": ["U", "V", "W"]})

    assert result["ok"], result
    hist = get_session().gpx.histograms()[0]
    assert bool(hist.data["Background"][0][1]) is True
    instrument = hist.data["Instrument Parameters"][0]
    for term in ("U", "V", "W"):
        assert instrument[term][2], "{} was dropped after the Background flag".format(term)

    # Clearing both in one call must also apply both.
    cleared = tools_refine.set_refinement(
        clear={"Background": True, "Instrument Parameters": ["U", "V", "W"]})
    assert cleared["ok"], cleared
    assert bool(hist.data["Background"][0][1]) is False
    for term in ("U", "V", "W"):
        assert not instrument[term][2], term


def test_set_refinement_cell(project) -> None:
    # With no phase in the project, GSAS-II applies the flag to zero phases
    # rather than complaining, so add a phase first and then enable the cell.
    from gsas2_mcp_server import tools_data
    assert tools_data.add_phase(phasename="Ph", cell=[8.48, 5.4, 6.96, 90, 90, 90])["ok"]

    result = tools_refine.set_refinement(set={"lattice": True})

    assert result["ok"], result
    phase = get_session().gpx.phase("Ph")
    assert phase["General"]["Cell"][0] is True


def test_set_refinement_clear(project) -> None:
    assert tools_refine.set_refinement(set={"Background": True})["ok"]
    result = tools_refine.set_refinement(clear={"bg": True})

    assert result["ok"], result
    assert result["applied"]["clear"] == {"Background": True}
    assert get_session().gpx.histograms()[0].data["Background"][0][1] is False


def test_set_refinement_requires_something_to_do(project) -> None:
    result = tools_refine.set_refinement()
    assert result["ok"] is False
    assert "Nothing to do" in result["error"]


def test_set_refinement_rejects_unknown_parameters(project) -> None:
    result = tools_refine.set_refinement(set={"NotARealParameter": True})
    assert result["ok"] is False
    assert "Unknown refinement key" in result["error"]
    assert "canonical name" in result["hint"]


def test_set_refinement_needs_a_project(engine_ready) -> None:
    result = tools_refine.set_refinement(set={"Background": True})
    assert result["ok"] is False
    assert "No project is open" in result["error"]


# --------------------------------------------------------------------------
# hold / free
# --------------------------------------------------------------------------

def test_hold_and_free_a_variable(linked_project) -> None:
    target = ":0:Scale"

    held = tools_refine.hold_variable([target])
    assert held["ok"], held
    assert held["affected"][0]["variable"] == target
    assert held["affected"][0]["held"] is True
    assert held["n_held_now"] == 1

    # Holding twice must not create a duplicate-free situation; freeing removes it.
    freed = tools_refine.free_variable([target])
    assert freed["ok"], freed
    assert freed["affected"][0]["held"] is False
    assert freed["not_found"] == []
    assert freed["n_held_now"] == 0


def test_free_reports_variables_that_were_never_held(linked_project) -> None:
    result = tools_refine.free_variable([":0:Zero"])
    assert result["ok"], result
    assert result["not_found"] == [":0:Zero"]
    assert result["affected"] == []


def test_hold_more_than_one_variable(linked_project) -> None:
    result = tools_refine.hold_variable([":0:Scale", ":0:Background"])
    assert result["ok"], result
    assert result["n_held_now"] == 2

    released = tools_refine.free_variable([":0:Scale", ":0:Background"])
    assert released["n_held_now"] == 0


def test_hold_requires_variables(linked_project) -> None:
    result = tools_refine.hold_variable([])
    assert result["ok"] is False
    assert "at least one variable" in result["error"]


def test_hold_rejects_a_nonsense_variable_name(linked_project) -> None:
    result = tools_refine.hold_variable(["this is not a variable name"])
    assert result["ok"] is False
    assert result["error"]


def test_hold_reports_when_a_phase_is_not_linked_to_data(project) -> None:
    """Addressing a variable by index needs a phase that uses the histogram.

    GSAS-II would otherwise silently drop the phase/histogram part of the name
    and attach the hold to the wrong scope, so the tool refuses instead.
    """
    result = tools_refine.hold_variable([":0:Scale"])

    assert result["ok"] is False
    assert result["error"]
    assert "phase" in result["hint"]


def test_hold_detects_an_out_of_range_histogram_index(linked_project) -> None:
    result = tools_refine.hold_variable([":7:Scale"])

    assert result["ok"] is False
    assert "histogram '7'" in result["error"]


def test_hold_detects_an_out_of_range_phase_index(linked_project) -> None:
    result = tools_refine.hold_variable(["9::A0"])

    assert result["ok"] is False
    assert "phase '9'" in result["error"]


# --------------------------------------------------------------------------
# refine / get_results
# --------------------------------------------------------------------------

def test_get_results_before_any_refinement(project) -> None:
    result = tools_refine.get_results()

    assert result["ok"], result
    assert result["refined"] is False
    assert result["Rwp"] == []
    assert result["n_refined_variables"] == 0
    assert result["n_refinements"] == 0
    assert len(result["histograms"]) == 1
    assert result["histograms"][0]["n_points"] == 6000


def test_refine_either_works_or_fails_with_the_documented_hint(project) -> None:
    tools_refine.set_refinement(set={"Background": True, "Scale": True})
    caps = engine.capabilities()
    result = tools_refine.refine()

    if caps.get("refinement_available"):
        assert result["ok"], result
        assert result["refined"] is True
        assert result["Rwp"] is not None
        assert result["least_squares"]
        assert result["n_refinements"] == 1
        # A successfully refined pattern must produce an R factor in range.
        assert 0.0 < float(result["Rwp"]) < 100.0
        hist = result["histograms"][0]
        assert hist["wR"] is not None
        assert hist["Rwp"] == hist["wR"]
    else:
        assert result["ok"] is False
        assert "pypowder" in result["hint"]
        assert result["capabilities"]["refinement_available"] is False


def test_refine_without_a_project(engine_ready) -> None:
    result = tools_refine.refine()
    assert result["ok"] is False
    assert "No project is open" in result["error"]


def test_get_results_never_raises_on_an_unrefined_project(project) -> None:
    """Reading results is safe at any point in a session."""
    first = tools_refine.get_results()
    tools_refine.set_refinement(set={"Background": True})
    second = tools_refine.get_results()
    assert first["ok"] and second["ok"]
    assert second["shifts"] == {}
    assert second["sigmas"] == {}


def test_phase_summary_and_flags_shape(project) -> None:
    from gsas2_mcp_server import tools_data
    assert tools_data.add_phase(phasename="Ph", cell=[8.48, 5.4, 6.96, 90, 90, 90])["ok"]

    flags = tools_refine.phase_summary_and_flags(get_session().gpx)
    assert "histograms" in flags and "phases" in flags
    assert flags["histograms"][0]["name"].startswith("PWDR")
    assert flags["phases"][0]["name"] == "Ph"
