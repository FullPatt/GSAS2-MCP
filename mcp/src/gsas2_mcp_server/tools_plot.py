"""Plotting: the classic observed / calculated / difference powder pattern.

The plot is written to a file rather than returned as an image over the MCP
wire, which keeps the transport small and lets the caller decide where the
figure lands.
"""

from __future__ import annotations

import os
import pathlib
from typing import Any, Dict, Optional, Sequence

from . import engine
from .state import get_session

__all__ = ["generate_plot", "TOOLS"]

#: Column layout of ``G2PwdrData.data['data'][1]`` (see ``G2PwdrData.plot``).
_COL_X, _COL_YOBS, _COL_YCALC, _COL_BACKGROUND, _COL_RESIDUAL = 0, 1, 3, 4, 5

_SUPPORTED_FORMATS = ("png", "svg", "pdf", "jpg", "jpeg", "tif", "tiff", "ps", "eps")


def _default_output(project_path: Optional[str], hist_name: str, fmt: str) -> str:
    """Pick a sensible output path next to the project file."""
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in hist_name).strip("_")
    directory = os.path.dirname(project_path) if project_path else os.getcwd()
    return os.path.join(directory or os.getcwd(), "{}_fit.{}".format(safe or "pattern", fmt))


def generate_plot(histogram: Optional[str] = None,
                  output: Optional[str] = None,
                  fmt: str = "png",
                  dpi: int = 150,
                  title: Optional[str] = None,
                  ymax: Optional[float] = None,
                  residual_offset: Optional[float] = None) -> Dict[str, Any]:
    """Write a fit plot for one histogram of the active project.

    Draws the observed pattern, the calculated pattern when a refinement has
    produced one, the background, and the difference curve below the pattern --
    the standard way to see *how* a fit fails, which the R factors alone do not
    reveal.

    :param histogram: histogram name; omit it when the project has exactly one
    :param output: file to write; defaults to ``<project_dir>/<histogram>_fit.<fmt>``
    :param fmt: ``png`` (default), ``svg``, ``pdf``, ``jpg``, ``tif``, ``eps``
    :param dpi: raster resolution for bitmap formats
    :param title: plot title; defaults to the histogram name and Rwp
    :param ymax: upper limit for the intensity axis, when the peaks dwarf the
        background and the useful detail is squashed
    :param residual_offset: vertical position of the difference curve,
        as a fraction of the intensity range (default: below the data)
    :returns: the path written, plus what was plotted and the data range
    """
    session = get_session()
    if not session.open:
        return engine.fail("No project is open.",
                           hint="Call create_project or load_project first.")
    suffix = (fmt or "png").lower().lstrip(".")
    if suffix not in _SUPPORTED_FORMATS:
        return engine.fail("Unsupported format {!r}.".format(fmt),
                           hint="Use one of: " + ", ".join(_SUPPORTED_FORMATS))
    try:
        gpx = session.gpx
        histograms = gpx.histograms()
        if not histograms:
            return engine.fail("The project has no powder data to plot.",
                               hint="Call add_powder_histogram first.")
        if histogram is None:
            if len(histograms) != 1:
                return engine.fail(
                    "The project has {} histograms; name the one to plot.".format(
                        len(histograms)),
                    available=[h.name for h in histograms])
            hist = histograms[0]
        else:
            hist = gpx.histogram(histogram)
            if hist is None:
                return engine.fail("No histogram named {!r}.".format(histogram),
                                   available=[h.name for h in histograms])

        target = output or _default_output(session.path, hist.name, suffix)
        target = os.path.abspath(os.path.expanduser(str(target)))
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)

        with engine.quiet():
            plotted = _draw(hist, target, dpi=int(dpi), title=title,
                            ymax=ymax, residual_offset=residual_offset)

        session.record("generate_plot", histogram=hist.name, output=target)
        return engine.ok(output=target, histogram=hist.name, format=suffix, **plotted)
    except Exception as exc:
        hint = "Check the histogram name with project_summary, and that the " \
               "output directory is writable."
        if "matplotlib" in str(exc).lower():
            hint = "matplotlib is required for plotting; install it in this environment."
        return engine.fail(exc, hint=hint)


def _draw(hist: Any, target: str, dpi: int, title: Optional[str],
          ymax: Optional[float], residual_offset: Optional[float]) -> Dict[str, Any]:
    """Render one pattern and return a description of what went into it."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    arrays = hist.data["data"][1]
    x = np.asarray(arrays[_COL_X], dtype=float)
    yobs = np.asarray(arrays[_COL_YOBS], dtype=float)
    ycalc = None
    background = None
    residual = None
    for index, name in ((_COL_YCALC, "ycalc"), (_COL_BACKGROUND, "background"),
                        (_COL_RESIDUAL, "residual")):
        try:
            values = np.asarray(arrays[index], dtype=float)
        except Exception:
            continue
        if values.size != x.size:
            continue
        if name == "ycalc" and np.any(values):
            ycalc = values
        elif name == "background" and np.any(values):
            background = values
        elif name == "residual":
            residual = values

    fig, (ax, ax_res) = plt.subplots(
        2, 1, figsize=(9.0, 5.4), dpi=dpi, sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08})

    ax.plot(x, yobs, ".", ms=2.0, color="#1f77b4", label="Observed")
    if ycalc is not None:
        ax.plot(x, ycalc, "-", lw=1.1, color="#d62728", label="Calculated")
    if background is not None:
        ax.plot(x, background, "--", lw=1.0, color="#2ca02c", label="Background")
    ax.set_ylabel("Intensity")
    if ymax is not None:
        ax.set_ylim(top=float(ymax))
    ax.legend(loc="best", fontsize=8, frameon=False)
    ax.grid(alpha=0.18, linewidth=0.6)

    if residual is not None:
        offset = 0.0 if residual_offset is None else float(residual_offset)
        ax_res.plot(x, residual + offset, "-", lw=0.9, color="#555555")
        ax_res.axhline(offset, color="#aaaaaa", lw=0.6, ls="--")
        ax_res.set_ylabel("Diff.", fontsize=8)
    else:
        ax_res.text(0.5, 0.5, "no calculated pattern yet - run refine",
                    ha="center", va="center", fontsize=8, color="#888888",
                    transform=ax_res.transAxes)
        ax_res.set_yticks([])
    ax_res.set_xlabel("2-theta (deg)" if _is_two_theta(hist) else "X")
    ax_res.grid(alpha=0.18, linewidth=0.6)

    rwp = None
    try:
        rwp = hist.get_wR()
    except Exception:
        pass
    if title is None:
        title = hist.name
        if rwp is not None:
            title += "   Rwp = {:.2f}%".format(rwp)
    ax.set_title(title, fontsize=10)

    fig.savefig(target, bbox_inches="tight")
    plt.close(fig)

    return {
        "n_points": int(x.size),
        "x_range": [float(x.min()), float(x.max())] if x.size else None,
        "has_calculated": ycalc is not None,
        "has_background": background is not None,
        "has_residual": residual is not None,
        "Rwp": rwp,
    }


def _is_two_theta(hist: Any) -> bool:
    """True when the histogram's x axis is 2-theta rather than TOF or Q."""
    try:
        return "T" not in hist.data["Instrument Parameters"][0]["Type"][0]
    except Exception:
        return True


TOOLS = (generate_plot,)
