"""MCP server assembly: collect the tools and expose them over a transport.

The MCP Python SDK renamed ``FastMCP`` to ``MCPServer`` in version 2.  Rather
than pinning one major version, this module imports whichever is present; the
decorator and ``add_tool`` surfaces used here are identical in both.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

from . import __version__
from . import tools_data, tools_diag, tools_plot, tools_project, tools_refine

__all__ = [
    "SERVER_NAME",
    "SERVER_VERSION",
    "SERVER_INSTRUCTIONS",
    "TOOL_MODULES",
    "all_tools",
    "build_server",
    "run_server",
]

SERVER_NAME = "gsas2-mcp"
SERVER_VERSION = __version__

SERVER_INSTRUCTIONS = (
    "GSAS-II crystallographic analysis: Rietveld and Le Bail refinement of "
    "powder diffraction data.\n"
    "\n"
    "Typical order of operations:\n"
    "1. create_project (or load_project).\n"
    "2. add_powder_histogram, then add_phase (or add_image for 2D data).\n"
    "3. set_refinement to choose what to fit, starting with Background and "
    "Scale, then Cell, then the profile terms.\n"
    "4. refine, then get_results.  Repeat steps 3-4, releasing one parameter "
    "group at a time.\n"
    "5. auto_diagnose when the fit stalls, generate_plot to *see* the "
    "mismatch, generate_report to record the outcome.\n"
    "\n"
    "Refinement quality is reported as Rwp (weighted profile R factor) and GoF. "
    "Every tool returns a JSON object with an 'ok' flag; on failure it also "
    "carries 'error', 'error_type' and usually a 'hint' explaining the fix.\n"
    "\n"
    "The compiled GSAS-II Fortran extensions are optional.  Without 'pypowder' "
    "the project, import, flag-setting, reporting and plotting tools all work, "
    "but refine reports a structured error instead of running."
)

#: Modules contributing tools, in the order they appear in the tool list.
TOOL_MODULES = (tools_project, tools_data, tools_refine, tools_diag, tools_plot)


def _server_class() -> type:
    """Return the MCP server class available in the installed SDK."""
    try:  # MCP SDK 1.x
        from mcp.server.fastmcp import FastMCP  # type: ignore
        return FastMCP
    except Exception:
        pass
    try:  # MCP SDK 2.x
        from mcp.server.mcpserver import MCPServer  # type: ignore
        return MCPServer
    except Exception as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError(
            "The 'mcp' package is required. Install it with 'pip install mcp'."
        ) from exc


def all_tools() -> Tuple[Callable[..., Any], ...]:
    """Every tool function this server exposes."""
    tools: List[Callable[..., Any]] = []
    for module in TOOL_MODULES:
        tools.extend(module.TOOLS)
    return tuple(tools)


def build_server(name: str = SERVER_NAME,
                 instructions: str = SERVER_INSTRUCTIONS) -> Any:
    """Create the MCP server with all tools registered.

    Returns an object with ``run(transport=...)``; the concrete class is
    :class:`mcp.server.mcpserver.MCPServer` on SDK 2.x and ``FastMCP`` on 1.x.
    """
    server_class = _server_class()
    kwargs: Dict[str, Any] = {"name": name, "instructions": instructions}
    try:
        server = server_class(**kwargs)
    except TypeError:  # pragma: no cover - very old SDK
        server = server_class(name=name)

    for tool in all_tools():
        server.add_tool(tool)
    return server


def run_server(transport: str = "stdio", host: str = "127.0.0.1",
               port: int = 8910) -> None:
    """Build the server and serve it until the client disconnects.

    :param transport: ``stdio`` (default, for Claude Desktop / Cursor /
        Cline and most IDE integrations), ``sse`` or ``streamable-http``
    :param host: bind address for the HTTP transports
    :param port: bind port for the HTTP transports
    """
    server = build_server()
    if transport != "stdio":
        settings = getattr(server, "settings", None)
        if settings is not None:
            try:
                settings.host = host
                settings.port = port
            except Exception:
                pass
    server.run(transport=transport)
