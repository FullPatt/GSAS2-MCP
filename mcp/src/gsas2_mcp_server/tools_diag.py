"""Diagnostics, refinement strategy and reporting.

These three tools turn raw numbers into something an agent (or a person) can
act on:

* :func:`auto_diagnose` inspects the project and reports concrete problems.
* :func:`suggest_best_strategy` lays out the conventional step-by-step
  refinement sequence, adapted to what the engine can actually do.
* :func:`generate_report` renders everything known about the project.

The numeric thresholds used here are the usual rules of thumb from Rietveld
practice.  They are reported alongside the measured value so the caller can
judge for themselves, and they are never presented as pass/fail absolutes.
"""

from __future__ import annotations

import datetime
import html
import json
import os
from typing import Any, Dict, List, Optional

from . import __version__, engine
from .tools_project import histogram_summary, phase_summary
from .tools_refine import get_results
from .state import get_session

__all__ = ["auto_diagnose", "suggest_best_strategy", "generate_report", "TOOLS"]

#: Conventional Rwp bands for a well-behaved laboratory powder pattern.
#: Reported as guidance only -- a large background or a poor model can make a
#: "good" number meaningless, and a difficult pattern can be perfectly
#: acceptable at a much higher one.
RWP_BANDS = ((10.0, "low"), (20.0, "moderate"), (float("inf"), "high"))

#: A refinement is treated as converged when no variable shifts by more than
#: this many estimated standard deviations in the last cycle.
CONVERGENCE_SHIFT_LIMIT = 1.0


def _rwp_band(value: float) -> str:
    for limit, label in RWP_BANDS:
        if value < limit:
            return label
    return "high"


def _finding(code: str, severity: str, message: str, evidence: Any = None,
             action: Any = None) -> Dict[str, Any]:
    item: Dict[str, Any] = {"code": code, "severity": severity, "message": message}
    if evidence is not None:
        item["evidence"] = evidence
    if action is not None:
        item["suggested_action"] = action
    return item


def auto_diagnose() -> Dict[str, Any]:
    """Inspect the active project and report what is wrong and what to try next.

    Checks, in order:

    * whether an engine capable of refinement is present at all;
    * whether there is data and at least one phase;
    * whether a refinement has been run, and if the numbers exist;
    * whether the last cycle converged (no shift larger than one ESD);
    * which parameter groups are still switched off, since fitting them is the
      usual next step when the fit is not yet good enough.

    Every finding carries the measured value it is based on and a concrete
    suggested action, so the result can be acted on directly.

    :returns: a severity, a list of findings, and a one-line summary
    """
    session = get_session()
    if not session.open:
        return engine.fail("No project is open.",
                           hint="Call create_project or load_project first.")

    findings: List[Dict[str, Any]] = []
    caps = engine.capabilities()

    if not caps.get("refinement_available", False):
        findings.append(_finding(
            "engine_no_refinement", "error",
            "The compiled 'pypowder' extension is missing, so no Rietveld or "
            "Le Bail refinement can be run in this environment.",
            evidence={"capabilities": caps},
            action="Build the Fortran extensions (README, Compilation) or move "
                   "the project to a platform that has them."))

    try:
        gpx = session.gpx
        hists = gpx.histograms()
        phases = gpx.phases()
    except Exception as exc:
        return engine.fail(exc)

    if not hists:
        findings.append(_finding("no_histograms", "warning",
                                 "The project has no powder data.",
                                 action="Call add_powder_histogram."))
    if not phases:
        findings.append(_finding("no_phases", "warning",
                                 "The project has no phases, so there is nothing "
                                 "to refine against.",
                                 action="Call add_phase, from a CIF or from scratch."))

    results = get_results()
    rwp_values: List[float] = []
    if results.get("ok"):
        for entry in results.get("histograms", []):
            if entry.get("Rwp") is not None:
                rwp_values.append(float(entry["Rwp"]))

    if not rwp_values:
        findings.append(_finding(
            "not_refined", "info",
            "No R factors are present yet, so nothing has been fitted.",
            action="Start with background and scale, then cell, then the profile "
                   "terms; see suggest_best_strategy."))
    else:
        worst = max(rwp_values)
        band = _rwp_band(worst)
        if band == "high":
            findings.append(_finding(
                "high_rwp", "warning",
                "Rwp is {:.2f}%, above the ~20% that usually indicates the model "
                "does not yet describe the data.".format(worst),
                evidence={"Rwp_percent": worst, "band": band},
                action="Check the background is being fitted, then the profile "
                       "width terms, then the structural model."))
        else:
            findings.append(_finding(
                "rwp_ok", "info",
                "Rwp is {:.2f}% ({} band).".format(worst, band),
                evidence={"Rwp_percent": worst, "band": band}))

        shifts = results.get("shifts") or {}
        sigmas = results.get("sigmas") or {}
        ratios = []
        for name, shift in shifts.items():
            sigma = sigmas.get(name)
            if sigma:
                ratios.append((abs(shift / sigma), name, shift, sigma))
        if ratios:
            ratios.sort(reverse=True)
            worst_ratio, worst_name, worst_shift, worst_sigma = ratios[0]
            if worst_ratio > CONVERGENCE_SHIFT_LIMIT:
                findings.append(_finding(
                    "not_converged", "warning",
                    "The largest shift is {:.2f} sigma ({}) -- the fit has not "
                    "settled.".format(worst_ratio, worst_name),
                    evidence={"variable": worst_name, "shift": worst_shift,
                              "sigma": worst_sigma, "ratio": worst_ratio,
                              "limit": CONVERGENCE_SHIFT_LIMIT},
                    action="Run refine again; if the shift stays large, fix the "
                           "correlated parameter with hold_variable."))
            else:
                findings.append(_finding(
                    "converged", "info",
                    "All shifts are below {:.1f} sigma; the fit has settled.".format(
                        CONVERGENCE_SHIFT_LIMIT),
                    evidence={"max_shift_over_sigma": worst_ratio,
                              "variable": worst_name}))

    # Which groups are still switched off?  Fitting them is the usual next step.
    pending: Dict[str, Any] = {}
    profile_terms = ("U", "V", "W", "X", "Y", "Z", "Zero", "SH/L")
    for hist in hists:
        try:
            if not hist.data["Background"][0][1]:
                pending.setdefault("Background", []).append(hist.name)
        except Exception:
            pass
        try:
            # Instrument parameter entries are [value, value, refine_flag].
            ip = hist.data["Instrument Parameters"][0]
            unfitted = [k for k in profile_terms
                        if isinstance(ip.get(k), (list, tuple)) and len(ip[k]) > 2
                        and not bool(ip[k][2])]
            if unfitted:
                pending.setdefault("Instrument Parameters", []).append(
                    {"histogram": hist.name, "terms": unfitted})
        except Exception:
            pass
    for ph in phases:
        try:
            if not ph["General"]["Cell"][0]:
                pending.setdefault("Cell", []).append(ph.name)
        except Exception:
            pass
        try:
            unrefined = [a.label for a in ph.atoms()
                         if "X" not in (a.refinement_flags or "")]
            if unrefined:
                pending.setdefault("Atoms", []).append(
                    {"phase": ph.name, "atoms": unrefined})
        except Exception:
            pass

    if pending:
        findings.append(_finding(
            "groups_not_fitted", "info",
            "These parameter groups are currently switched off: {}.".format(
                ", ".join(sorted(pending))),
            evidence=pending,
            action="Enable them step by step with set_refinement and re-run "
                   "refine after each step."))

    severities = [f["severity"] for f in findings]
    if "error" in severities:
        severity = "error"
    elif "warning" in severities:
        severity = "warning"
    else:
        severity = "info"

    summary = "{} finding(s); overall severity: {}.".format(len(findings), severity)
    if rwp_values:
        summary += " Rwp = {:.2f}%.".format(max(rwp_values))

    return engine.ok(severity=severity, summary=summary, findings=findings,
                     capabilities=caps)


def suggest_best_strategy() -> Dict[str, Any]:
    """Recommend the conventional incremental refinement sequence.

    Refining everything at once usually diverges; the standard practice is to
    release parameter groups in order of how strongly they affect the pattern,
    re-running the fit after each step so a bad step can be spotted
    immediately.  This tool returns that sequence, marks the steps that are
    already applied, and flags the ones this engine cannot perform.

    :returns: an ordered list of steps, each with the exact arguments to pass
        to ``set_refinement``
    """
    session = get_session()
    if not session.open:
        return engine.fail("No project is open.",
                           hint="Call create_project or load_project first.")
    caps = engine.capabilities()
    refinable = caps.get("refinement_available", False)

    steps: List[Dict[str, Any]] = [
        {
            "step": 1, "name": "Background and scale",
            "why": "The background shape and the overall intensity have the "
                   "largest effect on Rwp and are numerically well separated "
                   "from everything else, so they settle first.",
            "set_refinement": {"set": {"Background": True, "Scale": True}},
            "expect": "Rwp drops sharply; the residual stops showing a slow curve.",
        },
        {
            "step": 2, "name": "Unit cell",
            "why": "Peak positions depend on the cell; fixing them before the "
                   "profile avoids the cell absorbing profile errors.",
            "set_refinement": {"set": {"Cell": True}},
            "expect": "Peak positions align; the residual loses its "
                      "position-mismatch signature.",
        },
        {
            "step": 3, "name": "Profile width terms",
            "why": "U, V and W (plus Zero) control peak widths.  They come "
                   "after the cell because a wrong cell masquerades as a width "
                   "problem.",
            "set_refinement": {"set": {"Instrument Parameters": ["U", "V", "W", "Zero"]}},
            "expect": "Peak widths match; Rwp falls further.",
        },
        {
            "step": 4, "name": "Sample broadening",
            "why": "Crystallite size and microstrain refine the Lorentzian and "
                   "Gaussian broadening that U/V/W cannot express.",
            "set_refinement": {"set": {"Size": True, "Mustrain": True}},
            "expect": "Systematic width error across the pattern disappears.",
        },
        {
            "step": 5, "name": "Atomic coordinates",
            "why": "Only after positions, widths and background are right do "
                   "intensity-based parameters become meaningful.",
            "set_refinement": {"set": {"Atoms": {"all": "X"}}},
            "expect": "Relative peak intensities improve.",
        },
        {
            "step": 6, "name": "Atomic displacement parameters",
            "why": "Uiso is strongly correlated with occupancy and with the "
                   "background, so it is released last and watched closely.",
            "set_refinement": {"set": {"Atoms": {"all": "XU"}}},
            "expect": "Small Rwp gain; large shifts here mean over-fitting.",
        },
    ]

    applied: Dict[str, Any] = {}
    try:
        gpx = session.gpx
        for hist in gpx.histograms():
            try:
                applied.setdefault("Background", []).append(
                    bool(hist.data["Background"][0][1]))
            except Exception:
                pass
        for ph in gpx.phases():
            try:
                applied.setdefault("Cell", []).append(bool(ph["General"]["Cell"][0]))
            except Exception:
                pass
    except Exception:
        pass

    notes: List[str] = []
    if not refinable:
        notes.append(
            "This engine build has no 'pypowder' extension, so none of these "
            "steps can actually be executed here. The sequence is still the "
            "right plan for a complete GSAS-II build.")
    if not applied.get("Background"):
        notes.append("Nothing appears to be refined yet -- start at step 1.")
    notes.append(
        "Re-run refine after every step and stop releasing parameters when the "
        "shift-to-ESD ratios stay above ~1, which indicates over-fitting.")

    return engine.ok(steps=steps, current_flags=applied, notes=notes,
                     refinement_available=refinable,
                     capabilities=caps)


def generate_report(format: str = "markdown",   # noqa: A002 - MCP-facing name
                    output: Optional[str] = None) -> Dict[str, Any]:
    """Render a report of the active project as Markdown, HTML or JSON.

    Contains the project file, the engine's capabilities, every histogram with
    its R factors, every phase with its cell and atoms, the current refinement
    flags, and the session's activity log -- enough to hand a run to someone
    else or to attach to a record.

    :param format: ``markdown`` (default), ``html`` or ``json``
    :param output: optional file path; when given the report is written there
        and the path is returned alongside the content
    :returns: the report text and, if ``output`` was given, where it was written
    """
    session = get_session()
    if not session.open:
        return engine.fail("No project is open.",
                           hint="Call create_project or load_project first.")
    fmt = (format or "markdown").lower()
    if fmt in ("md", "markdown"):
        fmt = "markdown"
    if fmt not in ("markdown", "html", "json"):
        return engine.fail("Unsupported format {!r}.".format(format),
                           hint="Use 'markdown', 'html' or 'json'.")

    try:
        gpx = session.gpx
        results = get_results()
        data: Dict[str, Any] = {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "generator": {"name": "GSAS2-MCP", "version": __version__},
            "project": {
                "path": session.path,
                "histograms": [histogram_summary(h) for h in gpx.histograms()],
                "phases": [phase_summary(p) for p in gpx.phases()],
            },
            "results": {k: v for k, v in results.items() if k != "ok"},
            "capabilities": engine.capabilities(),
            "activity": session.log,
        }
        if fmt == "json":
            text = json.dumps(data, indent=2, default=str)
        else:
            body = _render_markdown(data)
            text = _markdown_to_html(body) if fmt == "html" else body

        payload: Dict[str, Any] = {"format": fmt, "content": text,
                                   "n_histograms": len(data["project"]["histograms"]),
                                   "n_phases": len(data["project"]["phases"])}
        if output:
            target = os.path.abspath(os.path.expanduser(str(output)))
            parent = os.path.dirname(target)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(target, "w", encoding="utf-8") as handle:
                handle.write(text)
            payload["output"] = target
            session.record("generate_report", format=fmt, output=target)
        else:
            session.record("generate_report", format=fmt)
        return engine.ok(**payload)
    except Exception as exc:
        return engine.fail(exc)


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return "{:.6g}".format(value)
    return str(value)


def _render_markdown(data: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# GSAS-II refinement report")
    lines.append("")
    lines.append("| | |")
    lines.append("|---|---|")
    lines.append("| Project | `{}` |".format(_fmt(data["project"]["path"])))
    lines.append("| Generated | {} |".format(data["generated_at"]))
    lines.append("| Engine | GSAS-II at `{}` |".format(
        _fmt(data["capabilities"].get("engine_root"))))
    lines.append("| Refinement available | {} |".format(
        data["capabilities"].get("refinement_available")))
    lines.append("")

    results = data.get("results") or {}
    if results.get("Rwp") is not None:
        lines.append("## Fit quality")
        lines.append("")
        lines.append("| Quantity | Value |")
        lines.append("|---|---|")
        rwp = results.get("Rwp")
        if isinstance(rwp, list):
            for index, value in enumerate(rwp):
                lines.append("| Rwp (histogram {}) | {}% |".format(index, _fmt(value)))
        else:
            lines.append("| Rwp | {}% |".format(_fmt(rwp)))
        lines.append("| GoF | {} |".format(_fmt(results.get("GoF"))))
        lines.append("| Refined variables | {} |".format(
            _fmt(results.get("n_refined_variables"))))
        lines.append("")

    histograms = data["project"]["histograms"]
    lines.append("## Histograms")
    lines.append("")
    if histograms:
        lines.append("| Name | Points | Rwp / wR (%) | R | Rb | wRb |")
        lines.append("|---|---|---|---|---|---|")
        for entry in histograms:
            res = entry.get("residuals") or {}
            lines.append("| {} | {} | {} | {} | {} | {} |".format(
                entry.get("name"), _fmt(entry.get("n_points")),
                _fmt(entry.get("wR")), _fmt(res.get("R")), _fmt(res.get("Rb")),
                _fmt(res.get("wRb"))))
    else:
        lines.append("_No powder data loaded._")
    lines.append("")

    phases = data["project"]["phases"]
    lines.append("## Phases")
    lines.append("")
    for entry in phases:
        lines.append("### {}".format(entry.get("name")))
        lines.append("")
        lines.append("- Space group: `{}`".format(_fmt(entry.get("space_group"))))
        cell = entry.get("cell") or {}
        if cell:
            lines.append("- Cell: a = {}, b = {}, c = {}, "
                         "alpha = {}, beta = {}, gamma = {}, V = {}".format(
                             _fmt(cell.get("length_a")), _fmt(cell.get("length_b")),
                             _fmt(cell.get("length_c")), _fmt(cell.get("angle_alpha")),
                             _fmt(cell.get("angle_beta")), _fmt(cell.get("angle_gamma")),
                             _fmt(cell.get("volume"))))
        atoms = entry.get("atoms") or []
        if atoms:
            lines.append("")
            lines.append("| Atom | Element | x | y | z | Occ | Refined |")
            lines.append("|---|---|---|---|---|---|---|")
            for atom in atoms:
                xyz = list(atom.get("coordinates") or [None, None, None])
                lines.append("| {} | {} | {} | {} | {} | {} | `{}` |".format(
                    atom.get("label"), atom.get("element"),
                    *[_fmt(v) for v in (xyz + [None, None, None])[:3]],
                    _fmt(atom.get("occupancy")), atom.get("refinement_flags")))
        lines.append("")

    caps = data["capabilities"]
    lines.append("## Engine capabilities")
    lines.append("")
    lines.append("| Module | Available |")
    lines.append("|---|---|")
    for key in sorted(k for k in caps if k.endswith("available")
                      or k in ("pyspg", "pypowder", "pytexture", "pydiffax",
                               "pack_f", "unpack_cbf", "histogram2d", "fmask")):
        lines.append("| {} | {} |".format(key, caps[key]))
    lines.append("")

    activity = data.get("activity") or []
    if activity:
        lines.append("## Activity")
        lines.append("")
        lines.append("| When | Action | Details |")
        lines.append("|---|---|---|")
        for entry in activity:
            details = {k: v for k, v in entry.items() if k not in ("at", "action")}
            lines.append("| {} | {} | {} |".format(
                entry.get("at"), entry.get("action"), _fmt(details or "")))
        lines.append("")

    return "\n".join(lines)


def _markdown_to_html(text: str) -> str:
    """Minimal Markdown to HTML conversion for the report's own output.

    Deliberately small: it handles only the constructs :func:`_render_markdown`
    emits (headings, tables, lists, bold markers and inline code), so no
    Markdown dependency is required.
    """
    out = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        "<title>GSAS-II refinement report</title>",
        "<style>",
        "body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:2rem;"
        "max-width:60rem;color:#1f2328;line-height:1.5}",
        "table{border-collapse:collapse;margin:1rem 0;font-size:.92em}",
        "th,td{border:1px solid #c9ccd1;padding:.35rem .6rem;text-align:left}",
        "th{background:#f2f4f6}",
        "h1{border-bottom:2px solid #c9ccd1;padding-bottom:.3rem}",
        "h2{margin-top:2rem;border-bottom:1px solid #e3e5e8;padding-bottom:.2rem}",
        "code{background:#f2f4f6;padding:.1rem .3rem;border-radius:3px}",
        "</style></head><body>",
    ]
    in_table = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") and c for c in cells):
                continue
            if not in_table:
                out.append("<table>")
                in_table = True
                out.append("<tr>" + "".join(
                    "<th>{}</th>".format(_inline_html(c)) for c in cells) + "</tr>")
            else:
                out.append("<tr>" + "".join(
                    "<td>{}</td>".format(_inline_html(c)) for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        if not line:
            continue
        if line.startswith("### "):
            out.append("<h3>{}</h3>".format(_inline_html(line[4:])))
        elif line.startswith("## "):
            out.append("<h2>{}</h2>".format(_inline_html(line[3:])))
        elif line.startswith("# "):
            out.append("<h1>{}</h1>".format(_inline_html(line[2:])))
        elif line.startswith("- "):
            out.append("<p>&bull; {}</p>".format(_inline_html(line[2:])))
        else:
            out.append("<p>{}</p>".format(_inline_html(line)))
    if in_table:
        out.append("</table>")
    out.append("</body></html>")
    return "\n".join(out)


def _inline_html(text: str) -> str:
    escaped = html.escape(text)
    while "`" in escaped:
        first = escaped.find("`")
        second = escaped.find("`", first + 1)
        if second == -1:
            break
        escaped = (escaped[:first] + "<code>" + escaped[first + 1:second]
                   + "</code>" + escaped[second + 1:])
    return escaped.replace("**", "")


TOOLS = (auto_diagnose, suggest_best_strategy, generate_report)
