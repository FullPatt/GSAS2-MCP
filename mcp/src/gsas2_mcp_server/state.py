"""Server-side session state.

The MCP tools are stateless from the client's point of view: an agent calls
``create_project``, then adds data, then refines.  Everything in between lives
here -- the open :class:`~GSASII.GSASIIscriptable.G2Project`, the file it is
bound to, and a log of what has been done.

Only one project is open at a time.  That mirrors how GSAS-II itself works (a
``.gpx`` file is the unit of work) and keeps the tool surface small.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

__all__ = ["Session", "SESSION", "get_session", "reset_session", "require_project"]


def _stamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Session:
    """Holds the currently open GSAS-II project and a short activity log."""

    #: Maximum number of log entries kept; the log is for orientation only.
    MAX_LOG = 200

    def __init__(self) -> None:
        self.gpx: Any = None
        self.path: Optional[str] = None
        self.log: List[Dict[str, Any]] = []
        self.refinements: List[Dict[str, Any]] = []
        self.last_results: Optional[Dict[str, Any]] = None

    # -- lifecycle ---------------------------------------------------------

    def attach(self, gpx: Any, path: str, action: str) -> None:
        """Bind a freshly created or loaded project to the session."""
        self.gpx = gpx
        self.path = path
        self.refinements = []
        self.last_results = None
        self.record(action, path=path)

    def close(self) -> None:
        """Forget the current project without touching its file."""
        self.gpx = None
        self.path = None
        self.refinements = []
        self.last_results = None

    def record(self, action: str, **details: Any) -> None:
        """Append an entry to the activity log, trimming the oldest entries."""
        entry: Dict[str, Any] = {"at": _stamp(), "action": action}
        entry.update(details)
        self.log.append(entry)
        if len(self.log) > self.MAX_LOG:
            del self.log[: len(self.log) - self.MAX_LOG]

    # -- accessors ---------------------------------------------------------

    @property
    def open(self) -> bool:
        return self.gpx is not None

    def require_project(self) -> Any:
        """Return the open project or raise a descriptive error."""
        if self.gpx is None:
            raise RuntimeError(
                "No project is open. Call create_project first (or load_project "
                "for an existing .gpx file).")
        return self.gpx

    def describe(self) -> Dict[str, Any]:
        """Compact description of the session, safe to serialise."""
        return {
            "project_open": self.open,
            "path": self.path,
            "n_histograms": len(self.gpx.histograms()) if self.open else 0,
            "n_phases": len(self.gpx.phases()) if self.open else 0,
            "n_refinements": len(self.refinements),
            "log_entries": len(self.log),
            "recent_activity": self.log[-5:],
        }


SESSION = Session()


def get_session() -> Session:
    """The process-wide session object."""
    return SESSION


def reset_session() -> Session:
    """Drop all state.  Used by the test-suite to isolate cases."""
    global SESSION
    SESSION = Session()
    return SESSION


def require_project() -> Any:
    """Shorthand for ``get_session().require_project()``."""
    return get_session().require_project()
