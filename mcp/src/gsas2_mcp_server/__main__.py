"""Command-line entry point: ``python -m gsas2_mcp_server``.

Examples::

    python -m gsas2_mcp_server                      # stdio, for IDE clients
    python -m gsas2_mcp_server --transport sse --port 8910
    python -m gsas2_mcp_server --check              # report what it can find
    python -m gsas2_mcp_server --engine /path/to/GSAS2-MCP

The ``--check`` mode is the quickest way to diagnose a broken install: it
reports whether GSAS-II was found and which compiled extensions are present.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from . import __version__, engine, server as server_module


def _force_utf8_streams() -> None:
    """Make console output survive non-UTF-8 code pages.

    On Windows the console defaults to a legacy code page (often GBK), where
    printing a symbol outside that page raises ``UnicodeEncodeError`` and kills
    the process.  A server that dies while logging is worse than one that logs
    a replacement character, so re-configure both streams.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def build_parser() -> argparse.ArgumentParser:
    """Command-line interface definition."""
    parser = argparse.ArgumentParser(
        prog="gsas2_mcp_server",
        description="MCP server exposing the GSAS-II diffraction analysis engine.")
    parser.add_argument("--version", action="version",
                        version="gsas2-mcp {}".format(__version__))
    parser.add_argument("--transport", default="stdio",
                        choices=("stdio", "sse", "streamable-http"),
                        help="transport to serve on (default: stdio)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address for the HTTP transports (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8910,
                        help="bind port for the HTTP transports (default: 8910)")
    parser.add_argument("--engine", default=None,
                        help="directory containing the GSASII/ package; overrides "
                             "the {} environment variable".format(engine.ENGINE_ENV_VAR))
    parser.add_argument("--check", action="store_true",
                        help="report the detected engine and tools, then exit")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Run the server, or the ``--check`` diagnostic."""
    _force_utf8_streams()
    args = build_parser().parse_args(argv)

    if args.engine:
        os.environ[engine.ENGINE_ENV_VAR] = args.engine
        engine.bootstrap(force=True)

    if args.check:
        return _check()

    try:
        server_module.run_server(transport=args.transport,
                                 host=args.host, port=args.port)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print("gsas2-mcp: {}: {}".format(type(exc).__name__, exc), file=sys.stderr)
        return 1
    return 0


def _check() -> int:
    """Print a diagnostic report of the engine and the registered tools."""
    report = {
        "server": server_module.SERVER_NAME,
        "version": __version__,
        "python": sys.version.split()[0],
    }
    try:
        import importlib.metadata as metadata
        report["mcp_sdk"] = metadata.version("mcp")
    except Exception:
        report["mcp_sdk"] = None
    report["server_class"] = server_module._server_class().__name__

    try:
        report["capabilities"] = engine.bootstrap()
        report["engine"] = str(engine.get_engine_root() or "<installed package>")
    except Exception as exc:
        report["engine_error"] = "{}: {}".format(type(exc).__name__, exc)

    tools = [tool.__name__ for tool in server_module.all_tools()]
    report["tools"] = tools
    report["n_tools"] = len(tools)

    print(json.dumps(report, indent=2))
    return 0 if "engine_error" not in report else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
