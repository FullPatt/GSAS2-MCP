"""End-to-end protocol test: run the server over stdio and talk MCP to it.

This is the test that proves the packaging actually works -- a real subprocess
is started with ``python -m gsas2_mcp_server``, the MCP handshake is performed,
and tools are listed and called through the protocol.  It catches problems that
unit tests cannot: a server that dies on import, whose stdout is polluted by
engine chatter, or whose tool schemas fail to serialise.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
from typing import Any, Dict, List

import anyio
import pytest

pytest.importorskip("mcp")

from mcp import ClientSession, StdioServerParameters, stdio_client  # noqa: E402

MCP_ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = MCP_ROOT.parent
SRC_ROOT = MCP_ROOT / "src"


def _server_params() -> StdioServerParameters:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["GSAS2_MCP_ENGINE"] = str(REPO_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "gsas2_mcp_server"],
        env=env,
        cwd=str(MCP_ROOT),
    )


async def _list_tools() -> List[Any]:
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return list(result.tools)


async def _call(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            payload = getattr(result, "structuredContent", None)
            if payload is None:
                texts = [block.text for block in result.content
                         if getattr(block, "type", None) == "text"]
                payload = json.loads(texts[0]) if texts else None
            return {"isError": bool(getattr(result, "isError", False)),
                    "payload": payload}


def test_server_lists_all_seventeen_tools() -> None:
    tools = anyio.run(_list_tools)

    names = [tool.name for tool in tools]
    assert len(names) == 17, names
    for expected in ("create_project", "load_project", "project_summary",
                     "save_project", "add_powder_histogram", "add_phase",
                     "add_image", "load_data", "set_refinement", "refine",
                     "get_results", "hold_variable", "free_variable",
                     "auto_diagnose", "suggest_best_strategy",
                     "generate_report", "generate_plot"):
        assert expected in names, expected


def _schema(tool: Any) -> Dict[str, Any]:
    """Input schema of a Tool, across MCP SDK versions.

    SDK 1.x exposes ``inputSchema``; SDK 2.x renamed it to ``input_schema``.
    """
    for attribute in ("input_schema", "inputSchema"):
        schema = getattr(tool, attribute, None)
        if schema is not None:
            return schema if isinstance(schema, dict) else schema.model_dump()
    return {}


def test_tool_schemas_are_usable() -> None:
    """Every tool must carry a description and a JSON schema with properties."""
    tools = anyio.run(_list_tools)

    for tool in tools:
        assert tool.description, "{} has no description".format(tool.name)
        schema = _schema(tool)
        assert schema.get("type") == "object", tool.name
        assert isinstance(schema.get("properties"), dict), tool.name
        assert len(tool.description) > 40, \
            "{} description is too thin to guide an agent".format(tool.name)


def test_required_arguments_are_marked(tmp_path) -> None:
    tools = anyio.run(_list_tools)
    by_name = {tool.name: tool for tool in tools}

    assert _schema(by_name["create_project"]).get("required") == ["path"]
    assert _schema(by_name["add_powder_histogram"]).get("required") == ["datafile"]
    assert _schema(by_name["load_data"]).get("required") == ["datafile"]
    # project_summary takes no arguments.
    assert _schema(by_name["project_summary"]).get("required", []) == []


def test_call_project_summary_without_a_project_returns_a_clean_error() -> None:
    """Failures come back as data, not as a broken transport."""
    result = anyio.run(lambda: _call("project_summary", {}))

    assert result["payload"]["ok"] is False
    assert "No project is open" in result["payload"]["error"]


def test_full_create_import_report_cycle_over_the_protocol(tmp_path) -> None:
    """Drive the whole chain through MCP and check the results survive the wire."""
    gpx = tmp_path / "protocol.gpx"
    data = REPO_ROOT / "tests" / "testinp" / "PBSO4.XRA"
    inst = REPO_ROOT / "tests" / "testinp" / "INST_XRY.PRM"
    if not (data.is_file() and inst.is_file()):
        pytest.skip("powder test data is missing from this checkout")

    async def _run() -> Dict[str, Any]:
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                out = {}

                async def call(name, args):
                    result = await session.call_tool(name, args)
                    payload = getattr(result, "structuredContent", None)
                    if payload is None:
                        texts = [b.text for b in result.content
                                 if getattr(b, "type", None) == "text"]
                        payload = json.loads(texts[0]) if texts else None
                    return payload

                out["create"] = await call("create_project", {"path": str(gpx)})
                out["add_hist"] = await call("add_powder_histogram",
                                             {"datafile": str(data),
                                              "iparams": str(inst)})
                out["add_phase"] = await call("add_phase",
                                              {"phasename": "PbSO4-P1",
                                               "cell": [8.48, 5.4, 6.96, 90, 90, 90]})
                out["set_ref"] = await call("set_refinement",
                                            {"set": {"bg": True, "scale": True}})
                out["summary"] = await call("project_summary", {})
                out["diagnose"] = await call("auto_diagnose", {})
                out["strategy"] = await call("suggest_best_strategy", {})
                out["report"] = await call("generate_report", {"format": "json"})
                out["plot"] = await call("generate_plot",
                                         {"output": str(tmp_path / "fit.png")})
                out["save"] = await call("save_project", {})
                return out

    results = anyio.run(_run)

    assert results["create"]["ok"], results["create"]
    assert results["add_hist"]["ok"], results["add_hist"]
    assert results["add_hist"]["histogram"]["n_points"] == 6000
    assert results["add_phase"]["ok"], results["add_phase"]
    assert results["set_ref"]["ok"], results["set_ref"]
    assert results["set_ref"]["applied"]["set"] == {"Background": True, "Scale": True}
    assert results["summary"]["ok"] and len(results["summary"]["histograms"]) == 1
    assert results["diagnose"]["ok"]
    assert len(results["strategy"]["steps"]) == 6
    assert results["report"]["ok"]
    report = json.loads(results["report"]["content"])
    assert report["project"]["phases"][0]["name"] == "PbSO4-P1"
    assert results["plot"]["ok"], results["plot"]
    assert (tmp_path / "fit.png").is_file()
    assert results["save"]["ok"]
    assert gpx.is_file()


def test_check_mode_exits_cleanly() -> None:
    """`--check` is the documented first thing to run when something is wrong."""
    import subprocess

    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["GSAS2_MCP_ENGINE"] = str(REPO_ROOT)
    completed = subprocess.run(
        [sys.executable, "-m", "gsas2_mcp_server", "--check"],
        capture_output=True, text=True, env=env, cwd=str(MCP_ROOT), timeout=180)

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["n_tools"] == 17
    assert report["capabilities"]["engine"] is True
    assert "engine_error" not in report
    # Engine chatter must not have leaked onto the JSON channel.
    assert "binary load error" not in completed.stdout
