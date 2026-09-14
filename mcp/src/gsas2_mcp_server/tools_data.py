"""Data import tools: powder patterns, phases, 2D images, and inspection.

Import calls are split in two on purpose:

* :func:`load_data` *peeks* at a file through the GSAS-II importer and reports
  what it contains, without touching the open project.  Useful before deciding
  whether a file is the right one.
* :func:`add_powder_histogram`, :func:`add_phase` and :func:`add_image` commit
  the data to the project.
"""

from __future__ import annotations

import os
import pathlib
from typing import Any, Dict, List, Optional, Sequence

from . import engine
from .tools_project import histogram_summary, phase_summary
from .state import get_session

__all__ = [
    "add_powder_histogram",
    "add_phase",
    "add_image",
    "load_data",
    "TOOLS",
]

#: Reader families exposed by GSAS-II; see ``GSASIIscriptable.Readers``.
_READER_KINDS = {
    "powder": "Pwdr",
    "phase": "Phase",
    "image": "Image",
    "single": "HKLF",
}

_PYSPG_HINT = (
    "This GSAS-II build has no compiled Fortran extensions (the 'pyspg' "
    "module is missing), so the space-group tables -- and therefore CIF import "
    "for any space group other than P 1 -- are unavailable. Build the "
    "extensions as described in the Compilation section of README.md, or "
    "create the phase explicitly with "
    "add_phase(phasename=..., spacegroup='P 1', cell=[...]).")


def _abs(path: str) -> str:
    return str(pathlib.Path(os.path.expanduser(str(path))).resolve())


def _looks_like_missing_extension(exc: BaseException) -> bool:
    text = "{} {}".format(type(exc).__name__, exc)
    return ("pyspg" in text) or ("pypowder" in text) or ("pydiffax" in text)


def add_powder_histogram(datafile: str, iparams: Optional[str] = None,
                         phases: Optional[Sequence[str]] = None,
                         fmthint: Optional[str] = None,
                         bank: Optional[int] = None) -> Dict[str, Any]:
    """Import a powder diffraction pattern into the active project.

    The histogram is linked to any phases named in ``phases``.  Most files need
    an instrument parameter file; pass the matching one in ``iparams``, or omit
    it for the few formats that carry their own instrument settings.

    :param datafile: the pattern to read.  ``.xra``/``.fxye``/``.gsas``/``.dat``
        and the other formats understood by the GSAS-II powder importers
    :param iparams: instrument parameter file, e.g. ``INST_XRY.PRM``
    :param phases: phase names to associate with the new histogram, or ``all``
    :param fmthint: restrict the importers tried to those whose format name
        contains this text (e.g. ``"GSAS"``); avoids guessing wrong
    :param bank: dataset number to read from a multi-bank file (1 = first)
    :returns: the new histogram's name and a summary of the project
    """
    try:
        target = _abs(datafile)
        if not os.path.exists(target):
            return engine.fail("No such data file: {}".format(target), path=target)
        inst = _abs(iparams) if iparams else None
        if inst and not os.path.exists(inst):
            return engine.fail("No such instrument parameter file: {}".format(inst),
                               path=inst)

        gpx = get_session().require_project()
        kwargs: Dict[str, Any] = {}
        if phases:
            kwargs["phases"] = list(phases)
        if fmthint:
            kwargs["fmthint"] = fmthint
        if bank is not None:
            kwargs["databank"] = int(bank)

        with engine.quiet():
            hist = gpx.add_powder_histogram(target, iparams=inst, **kwargs)
            gpx.save()

        get_session().record("add_powder_histogram", name=hist.name, path=target)
        return engine.ok(histogram=histogram_summary(hist), path=target,
                         n_histograms=len(gpx.histograms()))
    except Exception as exc:
        return engine.fail(exc, hint="Confirm the data and instrument files match "
                                     "and that the file format is supported.")


def add_phase(phasefile: Optional[str] = None,
              phasename: Optional[str] = None,
              histograms: Optional[Sequence[str]] = None,
              spacegroup: str = "P 1",
              cell: Optional[Sequence[float]] = None,
              fmthint: Optional[str] = None) -> Dict[str, Any]:
    """Add a crystallographic phase to the active project.

    Two ways to use it:

    * **From a file** -- pass ``phasefile`` (normally a ``.cif``) to read the
      structure, including its space group and atom list.
    * **From scratch** -- omit ``phasefile`` and pass ``phasename`` plus
      optionally ``spacegroup`` and ``cell``.  Atoms are added afterwards with
      the phase editing facilities of GSAS-II.

    :param phasefile: CIF or other structure file to read
    :param phasename: name for the phase; required when ``phasefile`` is omitted
    :param histograms: histogram names to associate with this phase.  Pass
        ``["all"]`` to link every histogram in the project.  When omitted, the
        new phase is linked to every histogram already in the project -- a
        Rietveld phase without data is never useful -- and the names actually
        linked are reported back as ``linked_histograms``
    :param spacegroup: space group symbol when building from scratch, e.g. ``P 1``
    :param cell: six unit cell parameters ``[a, b, c, alpha, beta, gamma]``
    :param fmthint: restrict the importers tried, e.g. ``"CIF"``
    :returns: the new phase's name, space group, cell and atoms
    """
    try:
        if phasefile is None and not phasename:
            return engine.fail(
                "Provide either phasefile, or phasename to build a phase from scratch.")
        gpx = get_session().require_project()

        wanted = [str(h) for h in (histograms or [])]
        if not wanted or any(h.lower() == "all" for h in wanted):
            wanted = [h.name for h in gpx.histograms()]
        else:
            # GSAS-II silently produces a broken phase when a history name does
            # not resolve, then dies with "'NoneType' object has no attribute
            # 'name'" inside its own code.  Check first and report the names
            # that do exist, so an agent can correct itself in one round trip.
            available = [h.name for h in gpx.histograms()]
            missing = [h for h in wanted if h not in available]
            if missing:
                return engine.fail(
                    "Unknown histogram name(s): {0}".format(", ".join(missing)),
                    hint=('Histograms in this project: {0}. Pass ["all"] to link '
                          'every histogram.').format(
                              ", ".join(available) if available
                              else "<none -- import a powder pattern first>"),
                    available_histograms=available)

        kwargs: Dict[str, Any] = {}
        if phasename:
            kwargs["phasename"] = phasename
        if wanted:
            kwargs["histograms"] = wanted
        if fmthint:
            kwargs["fmthint"] = fmthint
        if cell is not None:
            if len(cell) != 6:
                return engine.fail("cell must have six values [a, b, c, alpha, beta, gamma]")
            kwargs["cell"] = [float(v) for v in cell]

        target = None
        if phasefile is not None:
            target = _abs(phasefile)
            if not os.path.exists(target):
                return engine.fail("No such phase file: {}".format(target), path=target)

        with engine.quiet():
            phase = gpx.add_phase(target, spacegroup=spacegroup, **kwargs)
            gpx.save()

        if phase is None:
            return engine.fail(
                "GSAS-II did not return the new phase.",
                hint=_PYSPG_HINT if phasefile else "Check the phase name and cell.")

        get_session().record("add_phase", name=phase.name, path=target)
        return engine.ok(phase=phase_summary(phase), path=target,
                         linked_histograms=wanted,
                         n_phases=len(gpx.phases()))
    except Exception as exc:
        # CIF import goes through GSASIIspc, so its failure mode on a build
        # without the Fortran extensions is a generic "no reader could read
        # file".  Consult the engine's own capability report rather than
        # guessing from the message text.
        caps = engine.capabilities()
        if phasefile is not None and not caps.get("spacegroup_tables_available", True):
            hint = _PYSPG_HINT
        elif _looks_like_missing_extension(exc):
            hint = _PYSPG_HINT
        elif phasefile is not None:
            hint = ("Check the phase file is a valid CIF and that fmthint matches "
                    "its format.")
        else:
            hint = ("Building a phase from scratch needs a phasename and, for "
                    "anything other than P 1, the space-group tables; check the "
                    "space group symbol, the cell, and that the project has at "
                    "least one histogram.")
        return engine.fail(exc, hint=hint)


def add_image(imagefile: str,
              fmthint: Optional[str] = None,
              indexList: Optional[Sequence[int]] = None) -> Dict[str, Any]:
    """Load 2D detector image(s) into the active project.

    :param imagefile: the image to read (TIFF, MAR, CBF, EDF, GE, ADSC, ...)
    :param fmthint: restrict the importers tried, e.g. ``"TIF"``
    :param indexList: image numbers to keep from a multi-image file, 0-based
    :returns: names of the images added and the total image count
    """
    try:
        target = _abs(imagefile)
        if not os.path.exists(target):
            return engine.fail("No such image file: {}".format(target), path=target)
        kwargs: Dict[str, Any] = {}
        if fmthint:
            kwargs["fmthint"] = fmthint
        if indexList is not None:
            kwargs["indexList"] = [int(i) for i in indexList]

        gpx = get_session().require_project()
        with engine.quiet():
            result = gpx.add_image(target, **kwargs)
            gpx.save()

        images = result if isinstance(result, list) else [result]
        names = [getattr(i, "name", str(i)) for i in images]
        get_session().record("add_image", names=names, path=target)
        return engine.ok(images=names, path=target, n_images=len(gpx.images()))
    except Exception as exc:
        hint = _PYSPG_HINT if _looks_like_missing_extension(exc) else \
            "Check the file is a supported detector image and that image " \
            "importers are available in this GSAS-II build."
        return engine.fail(exc, hint=hint)


def load_data(datafile: str, kind: str = "auto",
              fmthint: Optional[str] = None) -> Dict[str, Any]:
    """Inspect a file with the GSAS-II importers without adding it to a project.

    Answers "what is in this file?" -- the detected format, how many data
    points, the angular range -- so an agent can pick the right file and the
    right importer before committing anything.  The open project is not
    modified.

    :param datafile: file to inspect
    :param kind: ``powder``, ``phase``, ``image``, ``single``, or ``auto`` to
        pick based on the file extension
    :param fmthint: restrict the importers tried, as in the import tools
    :returns: detected format and a description of the contents
    """
    try:
        target = _abs(datafile)
        if not os.path.exists(target):
            return engine.fail("No such file: {}".format(target), path=target)

        G2sc = engine.require_engine()
        with engine.quiet():
            G2sc.LoadG2fil()
            key = _READER_KINDS.get(kind.lower(), None)
            if key is None:
                key = _guess_reader_kind(target)
            readerlist = G2sc.Readers.get(key)
            if not readerlist:
                return engine.fail(
                    "No {} importers are available in this GSAS-II build.".format(key),
                    path=target, kind=key)
            readers = G2sc.import_generic(target, readerlist, fmthint=fmthint)

        if not readers:
            return engine.fail("No importer could read {}".format(target), path=target)

        info: Dict[str, Any] = {
            "path": target,
            "reader_kind": key,
            "size_bytes": os.path.getsize(target),
            "n_banks": len(readers),
            "banks": [],
        }
        for rd in readers:
            bank: Dict[str, Any] = {"format": getattr(rd, "formatName", None)}
            entry = getattr(rd, "powderentry", None)
            if entry:
                bank["idstring"] = entry[0]
                try:
                    bank["bank_numbers"] = list(entry[1])
                except Exception:
                    pass
            data = getattr(rd, "powderdata", None)
            if data:
                try:
                    x = data[0]
                    bank["n_points"] = int(len(x))
                    bank["x_min"] = float(min(x))
                    bank["x_max"] = float(max(x))
                    bank["n_columns"] = int(len(data))
                except Exception:
                    pass
            comments = getattr(rd, "comments", None)
            if comments:
                bank["comments"] = list(comments)[:10]
            info["banks"].append(bank)

        return engine.ok(**info)
    except Exception as exc:
        hint = _PYSPG_HINT if _looks_like_missing_extension(exc) else \
            "Try passing kind= and fmthint= to select the importer explicitly."
        return engine.fail(exc, hint=hint)


def _guess_reader_kind(path: str) -> str:
    """Pick a reader family from the file extension."""
    suffix = pathlib.Path(path).suffix.lower()
    if suffix in (".cif", ".mcif", ".magcif", ".pdb", ".jpd", ".gpx"):
        return "Phase"
    if suffix in (".tif", ".tiff", ".mar3450", ".mccd", ".cbf", ".edf",
                  ".adsc", ".img", ".ge1", ".ge2", ".ge3", ".ge4", ".ge5",
                  ".sum", ".h5", ".hdf5", ".sfrm"):
        return "Image"
    if suffix in (".hkl", ".fcf", ".int", ".hklf"):
        return "HKLF"
    return "Pwdr"


TOOLS = (add_powder_histogram, add_phase, add_image, load_data)
