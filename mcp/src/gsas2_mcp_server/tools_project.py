"""Project lifecycle tools: create, load, summarise and save a GSAS-II project.

A GSAS-II project is a ``.gpx`` file that bundles the diffraction data, the
phases, and the refinement settings.  Everything else in this server operates
on the project held by the current session.
"""

from __future__ import annotations

import os
import pathlib
from typing import Any, Dict, List, Optional

from . import engine
from .state import get_session

__all__ = [
    "create_project",
    "load_project",
    "project_summary",
    "save_project",
    "TOOLS",
]


# --------------------------------------------------------------------------
# helpers shared with the other tool modules
# --------------------------------------------------------------------------

def _norm_path(path: str) -> str:
    """Expand ``~`` and return an absolute path string."""
    return str(pathlib.Path(os.path.expanduser(str(path))).resolve())


def histogram_summary(hist: Any) -> Dict[str, Any]:
    """Compact, JSON-serialisable description of one powder histogram."""
    info: Dict[str, Any] = {"name": hist.name}
    try:
        arrays = hist.data["data"][1]
        info["n_points"] = int(len(arrays[0]))
    except Exception:
        info["n_points"] = None
    try:
        info["wR"] = hist.get_wR()
    except Exception:
        info["wR"] = None
    try:
        res = hist.residuals
        info["residuals"] = {k: res[k] for k in sorted(res)}
    except Exception:
        info["residuals"] = {}
    try:
        ip = hist.InstrumentParameters
        info["instrument_type"] = ip.get("Type", [None])[0]
        if ip.get("Source"):
            info["source"] = ip["Source"][0]
        # A monochromatic source stores one wavelength in 'Lam'; a K-alpha1/K-alpha2
        # doublet stores 'Lam1'/'Lam2'.
        wavelengths = []
        for key in ("Lam", "Lam1", "Lam2"):
            entry = ip.get(key)
            if isinstance(entry, (list, tuple)) and len(entry) > 1:
                wavelengths.append(entry[1])
        if wavelengths:
            info["wavelength"] = wavelengths
    except Exception:
        pass
    try:
        info["refinement_flags"] = {
            "background": bool(hist.data["Background"][0][1]),
            "instrument_parameters": sorted(
                k for k, v in hist.data["Instrument Parameters"][0].items()
                if isinstance(v, (list, tuple)) and len(v) > 2 and bool(v[2])),
            "limits": list(hist.data["Limits"][1]),
        }
    except Exception:
        pass
    return info


def phase_summary(phase: Any) -> Dict[str, Any]:
    """Compact, JSON-serialisable description of one crystallographic phase."""
    info: Dict[str, Any] = {"name": phase.name}
    try:
        info["cell"] = {k: float(v) for k, v in phase.get_cell().items()}
    except Exception:
        info["cell"] = None
    try:
        info["space_group"] = phase["General"]["SGData"]["SpGrp"]
    except Exception:
        info["space_group"] = None
    try:
        atoms = phase.atoms()
        info["n_atoms"] = len(atoms)
        info["atoms"] = [
            {"label": a.label, "element": a.element,
             "coordinates": [float(c) for c in a.coordinates],
             "occupancy": float(a.occupancy), "refinement_flags": a.refinement_flags}
            for a in atoms
        ]
    except Exception:
        info["n_atoms"] = None
    try:
        info["cell_refined"] = bool(phase["General"]["Cell"][0])
    except Exception:
        pass
    try:
        info["histograms"] = sorted(phase.histograms().keys())
    except Exception:
        try:
            info["histograms"] = sorted(phase.data["Histograms"].keys())
        except Exception:
            pass
    return info


# --------------------------------------------------------------------------
# tools
# --------------------------------------------------------------------------

def create_project(path: str, overwrite: bool = False,
                   author: Optional[str] = None) -> Dict[str, Any]:
    """Create a new, empty GSAS-II project and make it the active project.

    Call this before adding data.  The project is written to disk immediately
    as a ``.gpx`` file, which is the container GSAS-II uses for the data,
    phases and refinement settings.

    :param path: where to write the ``.gpx`` file (``~`` is expanded)
    :param overwrite: replace an existing file at that path; when False an
        existing file is an error rather than being silently truncated
    :param author: optional author name recorded in the project
    :returns: the active project's path and a summary of the empty project
    """
    try:
        target = _norm_path(path)
        if os.path.exists(target) and not overwrite:
            return engine.fail(
                "A file already exists at {}".format(target),
                hint="Pass overwrite=True to replace it, or choose another path.",
                path=target)
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        G2sc = engine.require_engine()
        session = get_session()
        with engine.quiet():
            gpx = G2sc.G2Project(newgpx=target, author=author)
            # Materialise the file now: GSAS-II only writes on demand, and an
            # agent that creates a project then crashes should still find it.
            gpx.save()
        session.attach(gpx, target, "create_project")
        return engine.ok(**{**project_summary(), "path": target})
    except Exception as exc:
        return engine.fail(exc, hint="Check the path is writable and GSAS-II is discoverable.")


def load_project(path: str) -> Dict[str, Any]:
    """Open an existing ``.gpx`` project and make it the active project.

    :param path: path to a ``.gpx`` file written by GSAS-II or this server
    :returns: the project's histograms, phases and refinement settings
    """
    try:
        target = _norm_path(path)
        if not os.path.exists(target):
            return engine.fail("No such file: {}".format(target), path=target)
        G2sc = engine.require_engine()
        session = get_session()
        with engine.quiet():
            gpx = G2sc.G2Project(gpxfile=target)
        session.attach(gpx, target, "load_project")
        return engine.ok(**{**project_summary(), "path": target})
    except Exception as exc:
        return engine.fail(exc, hint="Confirm the file is a GSAS-II .gpx project.")


def project_summary() -> Dict[str, Any]:
    """Return a structured summary of the active project.

    Reports the file path, the histograms with their point counts and R
    factors, the phases with their cells and atoms, and which refinement
    variables are currently switched on.  Useful as a cheap "what is the state
    of things" call between other operations, and as a progress check while an
    agent works through a refinement strategy.
    """
    that = get_session()
    if not that.open:
        return engine.fail(
            "No project is open.",
            hint="Call create_project or load_project first.",
            session=that.describe())
    try:
        gpx = that.gpx
        with engine.quiet():
            histograms = [histogram_summary(h) for h in gpx.histograms()]
            phases = [phase_summary(p) for p in gpx.phases()]
            controls = _read_controls(gpx)
        return engine.ok(
            path=that.path,
            histograms=histograms,
            phases=phases,
            controls=controls,
            capabilities=engine.capabilities(),
            session=that.describe(),
        )
    except Exception as exc:
        return engine.fail(exc)


#: Controls worth reporting.  Read straight from the project's Controls block
#: rather than through ``G2Project.get_Controls``, which prints the full list of
#: valid names and raises for anything unknown -- noise on a stdio transport.
_REPORTED_CONTROLS = ("max cyc", "shift factor", "deriv type", "min dM/M",
                      "newLeBail", "ShowCell", "Reverse Seq", "Author")


def _read_controls(gpx: Any) -> Dict[str, Any]:
    """Selected entries of the project's Controls block."""
    try:
        data = gpx.data["Controls"]["data"]
    except Exception:
        return {}
    return {key: data[key] for key in _REPORTED_CONTROLS if key in data}


def save_project(path: Optional[str] = None) -> Dict[str, Any]:
    """Save the active project, optionally to a new file.

    :param path: target ``.gpx`` path; when omitted the project is written
        back to the file it was created from or loaded from
    :returns: the path the project was written to
    """
    that = get_session()
    if not that.open:
        return engine.fail("No project is open.",
                           hint="Call create_project or load_project first.")
    try:
        target = _norm_path(path) if path else that.path
        with engine.quiet():
            that.gpx.save(target)
        that.path = target
        that.record("save_project", path=target)
        return engine.ok(path=target)
    except Exception as exc:
        return engine.fail(exc)


TOOLS = (create_project, load_project, project_summary, save_project)
