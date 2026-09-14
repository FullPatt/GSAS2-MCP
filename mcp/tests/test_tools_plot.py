"""Plot generation."""

from __future__ import annotations

import pathlib

import pytest

from gsas2_mcp_server import tools_plot, tools_project


def _png_header_ok(path: pathlib.Path) -> bool:
    with open(path, "rb") as handle:
        return handle.read(8) == b"\x89PNG\r\n\x1a\n"


def test_plot_defaults_to_a_file_next_to_the_project(project) -> None:
    result = tools_plot.generate_plot()

    assert result["ok"], result
    target = pathlib.Path(result["output"])
    assert target.is_file()
    assert target.parent == pathlib.Path(project).resolve().parent
    assert target.name.endswith("_fit.png")
    assert result["n_points"] == 6000
    assert result["x_range"][0] == pytest.approx(10.0, abs=0.01)
    assert result["format"] == "png"
    assert _png_header_ok(target)


def test_plot_has_no_calculated_curve_before_refining(project) -> None:
    """Without a refinement the plot must still render, and say so."""
    result = tools_plot.generate_plot()
    assert result["ok"], result
    assert result["has_calculated"] is False
    assert pathlib.Path(result["output"]).stat().st_size > 1000


def test_plot_to_an_explicit_path(project, tmp_path) -> None:
    target = tmp_path / "figures" / "pattern.png"
    result = tools_plot.generate_plot(output=str(target))

    assert result["ok"], result
    assert result["output"] == str(target.resolve())
    assert target.is_file()
    assert _png_header_ok(target)


def test_plot_svg_and_pdf(project, tmp_path) -> None:
    for suffix in ("svg", "pdf"):
        result = tools_plot.generate_plot(output=str(tmp_path / ("f." + suffix)),
                                          fmt=suffix)
        assert result["ok"], (suffix, result)
        assert pathlib.Path(result["output"]).stat().st_size > 500


def test_plot_rejects_an_unknown_format(project) -> None:
    result = tools_plot.generate_plot(fmt="bmp")
    assert result["ok"] is False
    assert "Unsupported format" in result["error"]


def test_plot_rejects_an_unknown_histogram(project) -> None:
    result = tools_plot.generate_plot(histogram="PWDR nothing")
    assert result["ok"] is False
    assert "No histogram named" in result["error"]
    assert result["available"]


def test_plot_needs_a_project() -> None:
    result = tools_plot.generate_plot()
    assert result["ok"] is False
    assert "No project is open" in result["error"]


def test_plot_needs_data(tmp_path, engine_ready) -> None:
    tools_project.create_project(str(tmp_path / "bare.gpx"))
    result = tools_plot.generate_plot()
    assert result["ok"] is False
    assert "no powder data" in result["error"]


def test_plot_honours_title_and_axis_limit(project, tmp_path) -> None:
    target = tmp_path / "custom.png"
    result = tools_plot.generate_plot(output=str(target), title="My pattern",
                                      ymax=5000.0, dpi=72)
    assert result["ok"], result
    assert target.is_file()


def test_plot_selects_the_named_histogram(project, tmp_path) -> None:
    """Passing a histogram name must resolve to that exact histogram."""
    summary = tools_project.project_summary()
    name = summary["histograms"][0]["name"]

    result = tools_plot.generate_plot(histogram=name,
                                      output=str(tmp_path / "by-name.png"))

    assert result["ok"], result
    assert result["histogram"] == name


def test_is_two_theta_detection(project) -> None:
    from gsas2_mcp_server.state import get_session
    hist = get_session().gpx.histograms()[0]
    assert tools_plot._is_two_theta(hist) is True


def test_default_output_sanitises_the_histogram_name() -> None:
    name = tools_plot._default_output("C:/data/proj.gpx", "PWDR a/b:c.XRA Bank 1", "png")
    assert name.endswith("_fit.png")
    assert "/" not in pathlib.Path(name).name
    assert ":" not in pathlib.Path(name).name
