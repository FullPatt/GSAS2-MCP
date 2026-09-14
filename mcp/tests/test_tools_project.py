"""Project lifecycle tools."""

from __future__ import annotations

import pathlib

from gsas2_mcp_server import tools_project
from gsas2_mcp_server.state import get_session


def test_create_project_writes_a_gpx(tmp_path: pathlib.Path, engine_ready: dict) -> None:
    target = tmp_path / "new.gpx"
    result = tools_project.create_project(str(target))

    assert result["ok"], result
    assert target.is_file()
    assert result["path"] == str(target.resolve())
    assert result["histograms"] == []
    assert result["phases"] == []
    assert get_session().open
    assert get_session().path == str(target.resolve())


def test_create_project_refuses_to_overwrite_by_default(tmp_path, engine_ready) -> None:
    target = tmp_path / "exists.gpx"
    target.write_text("a pre-existing file nobody wants to lose")

    result = tools_project.create_project(str(target))

    assert result["ok"] is False
    assert "already exists" in result["error"]
    assert "overwrite" in result["hint"]
    # The file is untouched.
    assert target.read_text() == "a pre-existing file nobody wants to lose"


def test_create_project_can_overwrite_when_asked(tmp_path, engine_ready) -> None:
    target = tmp_path / "overwrite.gpx"
    target.write_text("stale")

    result = tools_project.create_project(str(target), overwrite=True)

    assert result["ok"], result
    assert target.read_bytes()[:2] != b"st"


def test_create_project_makes_missing_directories(tmp_path, engine_ready) -> None:
    target = tmp_path / "deeper" / "nest" / "p.gpx"
    result = tools_project.create_project(str(target))
    assert result["ok"], result
    assert target.is_file()


def test_tilde_is_expanded(engine_ready) -> None:
    """`~` must be expanded before the path is handed to GSAS-II."""
    assert not pathlib.Path("~/x.gpx").is_absolute()
    resolved = tools_project._norm_path("~/x.gpx")
    assert pathlib.Path(resolved).is_absolute()
    assert "~" not in resolved


def test_project_summary_without_a_project_is_a_structured_error() -> None:
    result = tools_project.project_summary()
    assert result["ok"] is False
    assert "No project is open" in result["error"]
    assert "create_project" in result["hint"]
    assert result["session"]["project_open"] is False


def test_save_without_a_project_is_a_structured_error() -> None:
    result = tools_project.save_project()
    assert result["ok"] is False
    assert "No project" in result["error"]


def test_save_project_to_a_new_path(tmp_path, project) -> None:
    moved = tmp_path / "moved.gpx"
    result = tools_project.save_project(str(moved))

    assert result["ok"], result
    assert moved.is_file()
    assert get_session().path == str(moved.resolve())


def test_load_project_reopens_what_was_saved(tmp_path, project) -> None:
    first = tools_project.project_summary()
    assert first["ok"] and len(first["histograms"]) == 1
    names = [h["name"] for h in first["histograms"]]

    # Drop the live project so load_project has to read from disk.
    get_session().close()
    reloaded = tools_project.load_project(str(project))

    assert reloaded["ok"], reloaded
    assert [h["name"] for h in reloaded["histograms"]] == names


def test_load_project_missing_file(tmp_path, engine_ready) -> None:
    result = tools_project.load_project(str(tmp_path / "nope.gpx"))
    assert result["ok"] is False
    assert "No such file" in result["error"]


def test_load_project_rejects_a_non_project_file(tmp_path, engine_ready) -> None:
    bogus = tmp_path / "bogus.gpx"
    bogus.write_text("this is not a GSAS-II project")
    result = tools_project.load_project(str(bogus))
    assert result["ok"] is False
    assert result["error"]


def test_summary_reports_histogram_details(project) -> None:
    summary = tools_project.project_summary()
    assert summary["ok"], summary

    hist = summary["histograms"][0]
    assert hist["n_points"] > 1000
    assert "PBSO4" in hist["name"]
    # The Cu K-alpha doublet wavelengths come from INST_XRY.PRM.
    assert hist["wavelength"] == [1.5405, 1.5443]
    assert hist["instrument_type"] == "PXC"

    # Nothing has been refined, so no R factors exist yet.
    assert hist["wR"] is None
    assert hist["residuals"] == {}
    assert summary["capabilities"]["engine"] is True
    assert summary["session"]["n_histograms"] == 1


def test_summary_tracks_the_activity_log(project) -> None:
    summary = tools_project.project_summary()
    actions = [entry["action"] for entry in summary["session"]["recent_activity"]]
    assert "create_project" in actions
    assert "add_powder_histogram" in actions
