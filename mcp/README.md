# GSAS2-MCP — the MCP protocol layer

An [MCP](https://modelcontextprotocol.io) server that exposes the
[GSAS-II](https://github.com/AdvancedPhotonSource/GSAS-II) diffraction engine to
AI agents and scripted workflows.  This directory holds only the protocol
layer; the crystallographic engine lives in `../GSASII`.

```
AI agent (Claude / Copilot / Cursor …)
        │  MCP over stdio
        ▼
┌──────────────────────────┐   import   ┌────────────────────────┐
│  mcp/  (this directory)  │ ─────────→ │  ../GSASII  (engine)   │
│  gsas2_mcp_server        │            │  Rietveld / Le Bail    │
└──────────────────────────┘            └────────────────────────┘
```

## Install

```bash
# 1. the MCP layer
pip install /path/to/GSAS2-MCP/mcp

# 2. point it at the engine (a GSAS2-MCP checkout, i.e. the parent directory)
export GSAS2_MCP_ENGINE=/path/to/GSAS2-MCP      # Windows: set GSAS2_MCP_ENGINE=...
```

GSAS-II can also be installed into the same environment instead of being
referenced by path; the server checks for the environment variable first, then
for an importable `GSASII` package.

Check that everything resolved:

```bash
gsas2-mcp --check
```

That prints the detected engine, which compiled Fortran extensions are
available, and the list of registered tools.

## Run

```bash
python -m gsas2_mcp_server                                  # stdio (default)
python -m gsas2_mcp_server --transport sse --port 8910      # SSE over HTTP
python -m gsas2_mcp_server --transport streamable-http      # streamable HTTP
```

### Claude Desktop / Cursor / Cline

```json
{
  "mcpServers": {
    "gsas2-mcp": {
      "command": "python",
      "args": ["-m", "gsas2_mcp_server"],
      "env": {
        "GSAS2_MCP_ENGINE": "/path/to/GSAS2-MCP"
      }
    }
  }
}
```

## Tools (17)

| Area | Tool | Purpose |
|---|---|---|
| **Project** | `create_project` | create a new `.gpx` project |
| | `load_project` | open an existing `.gpx` project |
| | `project_summary` | histograms, phases, refinement flags, capabilities |
| | `save_project` | save, optionally to a new path |
| **Data** | `add_powder_histogram` | import a powder pattern (+ instrument file) |
| | `add_phase` | add a phase, from a CIF or built from scratch |
| | `add_image` | load 2D detector image(s) |
| | `load_data` | inspect a file with the importers *without* committing it |
| **Refinement** | `set_refinement` | switch parameters on/off, with shorthand names |
| | `refine` | run Rietveld / Le Bail |
| | `get_results` | Rwp, GoF, R factors, cell and ESDs, shifts |
| | `hold_variable` | fix a variable |
| | `free_variable` | release a held variable |
| **Diagnosis** | `auto_diagnose` | inspect the project, report problems and fixes |
| | `suggest_best_strategy` | the conventional step-by-step refinement sequence |
| | `generate_report` | report as Markdown / HTML / JSON |
| **Visualisation** | `generate_plot` | observed / calculated / difference plot |

Every tool returns a JSON object.  Success looks like `{"ok": true, ...}`;
failure looks like `{"ok": false, "error": ..., "error_type": ...,
"hint": ...}`.  Tools do not raise, so a failed call never breaks the
transport.

### Shorthand parameter names

`set_refinement` accepts GSAS-II's canonical names and a set of shorthands:

| Shorthand | Canonical |
|---|---|
| `bg`, `bkg` | `Background` |
| `inst`, `instr`, `instrument` | `Instrument Parameters` |
| `sample` | `Sample Parameters` |
| `lattice`, `unitcell`, `abc` | `Cell` |
| `coords`, `atom` | `Atoms` |
| `strain`, `microstrain` | `Mustrain` |
| `texture`, `pref.ori`, `po` | `Pref.Ori.` |
| `phasefraction`, `phasefrac` | `PhaseFraction` (= `Scale`) |
| `range`, `limits` | `Limits` |

## Example session

```
create_project(path="run.gpx")
add_powder_histogram(datafile="PBSO4.XRA", iparams="INST_XRY.PRM")
add_phase(phasefile="PbSO4-Wyckoff.cif")          # or: phasename=..., cell=[...]
set_refinement(set={"bg": True, "scale": True})
refine()
get_results()                    # Rwp, GoF, cell + ESD
set_refinement(set={"lattice": True})
refine()
auto_diagnose()                  # what is still unfitted, what to try next
generate_plot(output="fit.png")
generate_report(format="markdown", output="report.md")
```

Variables are addressed the way GSAS-II names them: `':0:Scale'` (histogram 0),
`'0::A0'` (cell parameter *a* of phase 0), `':0:U'` (profile term U),
`'0::A0:1'` (coordinate of atom 1).

## Engine capability handling

GSAS-II's compiled Fortran extensions (`pyspg`, `pypowder`, …) are optional at
the Python level.  The server probes for them at start-up and adapts:

| Component | Without the extension |
|---|---|
| `pyspg` (space group tables) | P 1 and P -1 still resolve, via the pure-Python fallback added to `GSASIIspc`; CIF import for other space groups returns a structured error naming `pyspg` |
| `pypowder` (profile calculation) | `refine` returns a structured error instead of running; every other tool keeps working |

So a Windows or compiler-less install can still create projects, import data,
set flags, hold/free variables, diagnose, report and plot — it just cannot
refine until the extensions are built.

## Where stdout goes

GSAS-II prints progress information to stdout, which on the stdio transport is
the JSON-RPC wire.  Every engine call is therefore wrapped so that Python-level
stdout is redirected to stderr (`gsas2_mcp_server.engine.quiet`).  The test
suite asserts that a full tool cycle leaves stdout completely empty.

## Tests

```bash
cd mcp
pip install -e ".[test]"
pytest -q
```

126 tests: engine discovery and the stdout guard, the space-group fallback,
all 17 tools including their error paths, and an end-to-end suite that starts
the server as a subprocess and drives it through a real MCP client over stdio.

## Licence

The MCP layer in this directory is BSD-3-Clause.  The GSAS-II engine in
`../GSASII` keeps its own licence (GSAS-II Open Source License, UChicago
Argonne LLC) — see `../LICENSE`.
