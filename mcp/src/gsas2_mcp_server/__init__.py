"""GSAS2-MCP: an MCP server exposing the GSAS-II diffraction analysis engine.

The package is a thin protocol layer.  All crystallographic work is delegated
to GSAS-II (:mod:`GSASII.GSASIIscriptable`); this package only discovers the
engine, keeps a project session, and exposes the operations as MCP tools.
"""

__version__ = "0.1.0"
__author__ = "FullPatt"
__license__ = "BSD-3-Clause"

__all__ = ["__version__", "__author__", "server", "engine"]
