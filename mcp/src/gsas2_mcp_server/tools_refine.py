"""Refinement control: set flags, run the fit, hold or free variables, read results.

Terminology used throughout, following GSAS-II:

* **Histogram parameters** -- ``Limits``, ``Sample Parameters``, ``Background``,
  ``Instrument Parameters``.
* **Phase parameters** -- ``Cell``, ``Atoms``, ``LeBail``.
* **HAP (histogram-and-phase) parameters** -- ``Scale``, ``Size``,
  ``Mustrain``, ``HStrain``, ``Pref.Ori.``, ``Extinction``, ``Babinet``.

:func:`set_refinement` accepts the canonical names above, but also common
shorthand (``bg``, ``lattice``, ``inst``, ``texture`` ...) which is expanded
via :data:`ABBREVIATIONS` before the call reaches GSAS-II.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import engine
from .tools_project import histogram_summary, phase_summary
from .state import get_session

__all__ = [
    "set_refinement",
    "refine",
    "get_results",
    "hold_variable",
    "free_variable",
    "ABBREVIATIONS",
    "TOOLS",
]

#: Canonical GSAS-II refinement keys, taken from
#: ``G2PwdrData.is_valid_refinement_key``, ``G2Phase.is_valid_refinement_key``
#: and ``G2Phase.is_valid_HAP_refinement_key``.
HISTOGRAM_KEYS = ("Limits", "Sample Parameters", "Background", "Instrument Parameters")
PHASE_KEYS = ("Cell", "Atoms", "LeBail")
HAP_KEYS = ("Babinet", "Extinction", "HStrain", "Mustrain", "Pref.Ori.", "Show",
            "Size", "Use", "Scale", "PhaseFraction")

#: Shorthand accepted by :func:`set_refinement`, mapped to canonical names.
#: Keys are normalised (lower case, no spaces, underscores, hyphens or dots).
ABBREVIATIONS: Dict[str, str] = {
    # histogram
    "limits": "Limits",
    "range": "Limits",
    "background": "Background", "bg": "Background", "bkg": "Background",
    "instrument": "Instrument Parameters", "instr": "Instrument Parameters",
    "inst": "Instrument Parameters", "iparams": "Instrument Parameters",
    "instrumentparameters": "Instrument Parameters",
    "sample": "Sample Parameters", "sampleparameters": "Sample Parameters",
    # phase
    "cell": "Cell", "lattice": "Cell", "unitcell": "Cell", "abc": "Cell",
    "atoms": "Atoms", "atom": "Atoms", "coords": "Atoms", "coordinates": "Atoms",
    "lebail": "LeBail",
    # histogram-and-phase
    "scale": "Scale", "phasefraction": "Scale", "phasefrac": "Scale",
    "size": "Size", "crystallitesize": "Size",
    "mustrain": "Mustrain", "strain": "Mustrain", "microstrain": "Mustrain",
    "hstrain": "HStrain", "hydrostaticstrain": "HStrain",
    "prefori": "Pref.Ori.", "preferredorientation": "Pref.Ori.",
    "texture": "Pref.Ori.", "po": "Pref.Ori.",
    "extinction": "Extinction", "babinet": "Babinet",
    "show": "Show", "use": "Use",
}

_HINT_MISSING_PROFILE = (
    "Rietveld refinement needs the compiled 'pypowder' extension, which is not "
    "available in this GSAS-II build. Build the Fortran extensions (see the "
    "Compilation section of README.md) or run on a platform that provides them."
)


def _normalise_key(key: str) -> str:
    """Lower-case a key and strip separators, for abbreviation lookup."""
    return re.sub(r"[\s_\-.]+", "", str(key)).lower()


def _resolve_key(key: str) -> str:
    """Expand an abbreviation to its canonical GSAS-II name.

    Canonical names pass through unchanged (matching case-insensitively), so
    callers that use the real names are never affected by the table.
    """
    text = str(key)
    for candidate in HISTOGRAM_KEYS + PHASE_KEYS + HAP_KEYS:
        if text == candidate or _normalise_key(text) == _normalise_key(candidate):
            return candidate
    resolved = ABBREVIATIONS.get(_normalise_key(text))
    return resolved if resolved is not None else text


def _resolve_mapping(mapping: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Resolve every key in *mapping*; return the resolved dict and the renames."""
    resolved: Dict[str, Any] = {}
    renames: Dict[str, str] = {}
    for key, value in (mapping or {}).items():
        name = _resolve_key(key)
        resolved[name] = value
        if name != key:
            renames[str(key)] = name
    return resolved, renames


def set_refinement(set: Optional[Dict[str, Any]] = None,       # noqa: A002 - MCP-facing name
                   clear: Optional[Dict[str, Any]] = None,
                   histogram: Any = "all",
                   phase: Any = "all") -> Dict[str, Any]:
    """Switch refinement variables on or off on the active project.

    This is the tool that decides *what the next refinement will fit*.

    Canonical keys (shorthand in brackets) are:

    * histogram -- ``Limits`` (``range``), ``Background`` (``bg``),
      ``Instrument Parameters`` (``inst``), ``Sample Parameters`` (``sample``)
    * phase -- ``Cell`` (``lattice``), ``Atoms`` (``coords``), ``LeBail``
    * histogram-and-phase -- ``Scale`` (``phasefraction``), ``Size``,
      ``Mustrain`` (``strain``), ``HStrain``, ``Pref.Ori.`` (``texture``),
      ``Extinction``, ``Babinet``

    Values are passed through to GSAS-II unchanged, so ``{"Background": True}``,
    ``{"Background": {"type": "chebyschev-1", "no. coeffs": 6, "refine": True}}``,
    ``{"Cell": True}`` and ``{"Atoms": {"all": "XU"}}`` all work.  For
    ``Instrument Parameters`` and ``Sample Parameters`` pass a list of names,
    e.g. ``{"Instrument Parameters": ["U", "V", "W"]}``.

    A typical incremental strategy is to fit one group at a time and re-run
    :func:`refine` after each call.

    :param set: parameters to switch on
    :param clear: parameters to switch off
    :param histogram: ``all`` (default), a histogram name, index, or a list
    :param phase: ``all`` (default), a phase name, index, or a list
    :returns: what was actually applied, after abbreviation expansion
    """
    if not set and not clear:
        return engine.fail("Nothing to do: pass set= and/or clear=.",
                           hint="Example: set_refinement(set={'Background': True, 'Scale': True})")
    try:
        on, on_renames = _resolve_mapping(set or {})
        off, off_renames = _resolve_mapping(clear or {})
        gpx = get_session().require_project()
        with engine.quiet():
            gpx.set_refinement({"set": on, "clear": off},
                               histogram=histogram, phase=phase)
            gpx.save()
        get_session().record("set_refinement", set=sorted(on), clear=sorted(off),
                             histogram=histogram, phase=phase)
        return engine.ok(applied={"set": on, "clear": off},
                         renamed={**on_renames, **off_renames},
                         histogram=histogram, phase=phase,
                         project=phase_summary_and_flags(gpx))
    except Exception as exc:
        hint = "Check the parameter names against the list in this tool's description."
        if "Unknown refinement key" in str(exc):
            hint = ("Unknown parameter. Pass a canonical name such as 'Background', "
                    "'Cell', 'Scale', 'Size', 'Mustrain', 'Instrument Parameters'.")
        return engine.fail(exc, hint=hint)


def phase_summary_and_flags(gpx: Any) -> Dict[str, Any]:
    """Small helper: refinement flags that are currently switched on."""
    flags: Dict[str, Any] = {"histograms": [], "phases": []}
    try:
        for hist in gpx.histograms():
            entry = {"name": hist.name}
            try:
                entry["background"] = bool(hist.data["Background"][0][1])
            except Exception:
                pass
            try:
                # Instrument parameter entries are [value, value, refine_flag];
                # the flag is an int (0/1), not a bool.
                entry["instrument_parameters"] = sorted(
                    k for k, v in hist.data["Instrument Parameters"][0].items()
                    if isinstance(v, (list, tuple)) and len(v) > 2 and bool(v[2]))
            except Exception:
                pass
            flags["histograms"].append(entry)
    except Exception:
        pass
    try:
        for ph in gpx.phases():
            entry = {"name": ph.name}
            try:
                entry["cell"] = bool(ph["General"]["Cell"][0])
            except Exception:
                pass
            try:
                entry["atoms"] = {a.label: a.refinement_flags for a in ph.atoms()}
            except Exception:
                pass
            try:
                entry["HAP"] = {k: v for k, v in ph.getHAPvalues(
                    gpx.histograms()[0].name).items() if v}
            except Exception:
                pass
            flags["phases"].append(entry)
    except Exception:
        pass
    return flags


def refine(printFile: Optional[str] = None,   # noqa: N803 - GSAS-II spelling
           makeBack: bool = False) -> Dict[str, Any]:   # noqa: N803
    """Run a Rietveld (or Le Bail) refinement on the active project.

    Uses whatever flags :func:`set_refinement` last switched on.  The project
    is saved before the fit and the fit results are written back into it, so
    :func:`get_results` and :func:`generate_plot` see the new state.

    :param printFile: optional path; GSAS-II's least-squares log is echoed there
    :param makeBack: keep a ``.bak`` copy of the project before refining
    :returns: R factors for every histogram plus the total shift/ESD summary
    """
    session = get_session()
    if not session.open:
        return engine.fail("No project is open.",
                           hint="Call create_project or load_project first.")
    try:
        caps = engine.capabilities()
        if caps and not caps.get("refinement_available", True):
            return engine.fail(
                "This GSAS-II build cannot refine: the compiled 'pypowder' "
                "extension is missing.",
                hint=_HINT_MISSING_PROFILE,
                capabilities=caps)
        gpx = session.gpx
        kwargs: Dict[str, Any] = {"makeBack": bool(makeBack)}
        if printFile:
            kwargs["printFile"] = str(printFile)
        with engine.quiet():
            results = gpx.refine(**kwargs)
            gpx.save()
        rvals = {}
        if isinstance(results, dict):
            for key in ("Rwp", "GOF", "chisq", "Nobs", "Nvars", "Nobs/Nvar"):
                if key in results:
                    try:
                        rvals[key] = float(results[key])
                    except (TypeError, ValueError):
                        rvals[key] = results[key]
        session.refinements.append({"n": len(session.refinements) + 1,
                                    "Rwp": rvals.get("Rwp"),
                                    "GOF": rvals.get("GOF")})
        session.last_results = rvals
        session.record("refine", makeBack=bool(makeBack))
        payload = get_results()
        payload["ok"] = True
        payload["refinement_index"] = len(session.refinements)
        payload["least_squares"] = rvals
        return payload
    except Exception as exc:
        text = str(exc)
        hint = _HINT_MISSING_PROFILE if ("pypowder" in text or "pyspg" in text) else \
            "Review the refinement flags with project_summary, and consider " \
            "fitting fewer variables at a time."
        return engine.fail(exc, hint=hint)


def get_results() -> Dict[str, Any]:
    """Read the current refinement results out of the active project.

    Reports the weighted profile R factor (Rwp), the unweighted and Bragg
    R factors, and the refined unit cell parameters with their estimated
    standard deviations when a covariance matrix is available.

    Before any refinement has run the R factors are absent, which is reported
    as ``refined: false`` rather than an error.
    """
    session = get_session()
    if not session.open:
        return engine.fail("No project is open.",
                           hint="Call create_project or load_project first.")
    try:
        gpx = session.gpx
        histograms = []
        for hist in gpx.histograms():
            entry = histogram_summary(hist)
            entry["Rwp"] = entry.get("wR")
            histograms.append(entry)
        phases = []
        for ph in gpx.phases():
            entry = phase_summary(ph)
            try:
                cell, esd = ph.get_cell_and_esd()
                entry["cell_esd"] = {k: float(v) for k, v in esd.items()}
            except Exception:
                pass
            phases.append(entry)

        shifts: Dict[str, float] = {}
        sigmas: Dict[str, float] = {}
        try:
            with engine.quiet():
                raw_shifts, raw_sigmas = gpx.get_LastFitResults()
            shifts = {k: float(v) for k, v in (raw_shifts or {}).items()}
            sigmas = {k: float(v) for k, v in (raw_sigmas or {}).items()}
        except Exception:
            pass

        rwp = [h["Rwp"] for h in histograms if h.get("Rwp") is not None]
        return engine.ok(
            refined=bool(rwp),
            Rwp=rwp[0] if len(rwp) == 1 else rwp,
            GoF=(session.last_results or {}).get("GOF"),
            histograms=histograms,
            phases=phases,
            n_refined_variables=len(shifts),
            shifts=shifts,
            sigmas=sigmas,
            least_squares=session.last_results,
            n_refinements=len(session.refinements),
        )
    except Exception as exc:
        return engine.fail(exc)


def _constraint_scope(G2sc: Any, var: Any) -> str:
    """Constraint scope ('Hist', 'Phase', 'HAP' or 'Global') for a variable."""
    try:
        return G2sc._constr_type(var)
    except Exception:
        phase = getattr(var, "phase", None)
        hist = getattr(var, "histogram", None)
        if hist and phase:
            return "HAP"
        if phase:
            return "Phase"
        if hist:
            return "Hist"
        return "Global"


def hold_variable(variables: Sequence[Any],
                  ctype: Optional[str] = None) -> Dict[str, Any]:
    """Hold (fix) variables so the next refinement leaves them alone.

    Variables are named GSAS-II style, as ``phase:histogram:name:atom`` with
    numeric indices:

    * ``':0:Scale'`` -- scale factor of histogram 0;
    * ``'0::A0'`` -- cell parameter *a* of phase 0;
    * ``':0:U'`` -- profile width term U of histogram 0;
    * ``'0::A0:1'`` -- coordinate of atom 1 in phase 0.

    The constraint scope (``Hist``, ``HAP``, ``Phase`` or ``Global``) is derived
    from the variable, so ``ctype`` is rarely needed.

    :param variables: variable names to hold
    :param ctype: force a scope -- ``Hist``, ``Phase``, ``HAP`` or ``Global``
    :returns: the variables now held
    """
    return _apply_holds(variables, ctype, hold=True)


def free_variable(variables: Sequence[Any],
                  ctype: Optional[str] = None) -> Dict[str, Any]:
    """Release variables previously held by :func:`hold_variable`.

    Removes the matching hold constraints from the project.  Variables that
    were not held are reported back in ``not_found``, so a typo is visible
    rather than silently ignored.

    :param variables: variable names to release
    :param ctype: restrict the search to one scope, otherwise all are searched
    :returns: the variables released, and any that had no hold to remove
    """
    return _apply_holds(variables, ctype, hold=False)


def _to_var_obj(gpx: Any, item: Any) -> Any:
    """Turn a variable name or tuple into a ``G2VarObj``.

    GSAS-II addresses variables by *index* into the project's phase, histogram
    and atom lists, and those indices live in the module-level ``*IdLookup``
    dictionaries that ``G2Project.index_ids()`` fills in.  So the index has to
    be refreshed before a name like ``':0:Scale'`` can be understood; the
    caller does that once, up front.
    """
    if isinstance(item, str) or isinstance(item, (list, tuple)):
        return gpx.make_var_obj(item, reloadIdx=False)
    return item


def _unresolved_reference(spec: Any, var: Any) -> Optional[str]:
    """Describe a name whose numeric phase/histogram reference did not resolve.

    Without a fresh index GSAS-II silently drops the parts of a variable name
    it cannot map, turning ``':0:Scale'`` into a histogram-less ``'Scale'``.
    That is worse than failing, because the resulting hold would be attached to
    the wrong scope -- so it is detected and reported here.
    """
    if not isinstance(spec, str) or spec.count(":") < 2:
        return None
    fields = spec.split(":")
    phase_field, hist_field = fields[0], fields[1]
    if phase_field not in ("", "*") and getattr(var, "phase", None) is None:
        return ("phase {!r} did not resolve to a phase in this project".format(
            phase_field))
    if hist_field not in ("", "*") and getattr(var, "histogram", None) is None:
        return ("histogram {!r} did not resolve to a histogram linked to a "
                "phase".format(hist_field))
    return None


def _apply_holds(variables: Sequence[Any], ctype: Optional[str],
                 hold: bool) -> Dict[str, Any]:
    if not variables:
        return engine.fail("Pass at least one variable, e.g. variables=[':0:Scale'].")
    session = get_session()
    if not session.open:
        return engine.fail("No project is open.",
                           hint="Call create_project or load_project first.")
    try:
        G2sc = engine.require_engine()
        gpx = session.gpx
        scopes = [ctype] if ctype else ["Hist", "HAP", "Phase", "Global"]
        affected: List[Dict[str, Any]] = []
        untouched: List[str] = []

        with engine.quiet():
            # Refresh the phase/histogram/atom id index that variable names are
            # resolved against.  This also saves the project.
            try:
                gpx.index_ids()
            except Exception as exc:
                return engine.fail(
                    exc,
                    hint="GSAS-II variable names are addressed by index, so the "
                         "project must contain at least one phase linked to a "
                         "histogram. Add one with add_phase(histograms=['all']).")

            targets = []
            for item in variables:
                var = _to_var_obj(gpx, item)
                problem = _unresolved_reference(item, var)
                if problem:
                    return engine.fail(
                        "Cannot resolve variable {!r}: {}.".format(item, problem),
                        hint="Variable names look like ':0:Scale' (histogram 0) or "
                             "'0::A0' (phase 0). Check the indices against "
                             "project_summary, and make sure the phase is linked "
                             "to the histogram: add_phase(histograms=['all']).")
                targets.append((item, var))

            for item, var in targets:
                name = str(var)
                if hold:
                    scope = ctype or _constraint_scope(G2sc, var)
                    gpx.add_constraint_raw(scope, [[1.0, var], None, None, "h"])
                    affected.append({"variable": name, "scope": scope, "held": True})
                else:
                    removed = False
                    for scope in scopes:
                        try:
                            bucket = gpx.get_Constraints(scope)
                        except Exception:
                            continue
                        for entry in list(bucket):
                            try:
                                entry_var = entry[0][1]
                            except Exception:
                                continue
                            if str(entry_var) == name and len(entry) > 3 and entry[3] == "h":
                                bucket.remove(entry)
                                affected.append({"variable": name, "scope": scope,
                                                 "held": False})
                                removed = True
                                break
                        if removed:
                            break
                    if not removed:
                        untouched.append(name)
            if affected:
                gpx.save()
        session.record("hold_variable" if hold else "free_variable",
                       variables=[a["variable"] for a in affected])
        return engine.ok(action="hold" if hold else "free",
                         affected=affected,
                         not_found=untouched,
                         n_held_now=_count_holds(gpx, ["Hist", "HAP", "Phase", "Global"]))
    except Exception as exc:
        return engine.fail(exc,
                           hint="Variable names look like ':0:Scale' or '0::A0'; "
                                "check the phase/histogram indices in project_summary.")


def _count_holds(gpx: Any, scopes: Sequence[str]) -> int:
    total = 0
    for scope in scopes:
        try:
            for entry in gpx.get_Constraints(scope):
                if len(entry) > 3 and entry[3] == "h":
                    total += 1
        except Exception:
            continue
    return total


TOOLS = (set_refinement, refine, get_results, hold_variable, free_variable)
