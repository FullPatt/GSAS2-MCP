"""Shared fixtures for the GSAS2-MCP test-suite.

The tests are written to run on any machine that has the GSAS-II *source*,
with or without the compiled Fortran extensions:

* tools that need no extension (project handling, data import, flag setting,
  reporting, plotting) are asserted to succeed;
* refinement is asserted to either work, or to fail with the documented
  structured error -- never with an unhandled traceback.

``GSAS2_MCP_ENGINE`` is pointed at the repository root so the tests exercise
the checkout under test rather than an installed GSAS-II.
"""

from __future__ import annotations

import os
import pathlib
import struct
import sys
from typing import Iterator

import pytest

MCP_ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = MCP_ROOT.parent
SRC_ROOT = MCP_ROOT / "src"
TESTINP = REPO_ROOT / "tests" / "testinp"

# The package is used from the source tree; no installation step required.
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# Put the checkout under test on sys.path at collection time, so that test
# modules which import GSASII directly (see test_p1_fallback.py) work without
# waiting for the engine bootstrap fixture.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Make sure the engine under test is this checkout.
os.environ.setdefault("GSAS2_MCP_ENGINE", str(REPO_ROOT))
os.environ.setdefault("GSASII_HEADLESS", "true")
os.environ.setdefault("MPLBACKEND", "Agg")


def write_gray_tiff(path: pathlib.Path, width: int = 64, height: int = 64) -> pathlib.Path:
    """Write a minimal uncompressed 16-bit grayscale baseline TIFF.

    Hand-rolled so the test-suite does not depend on Pillow.  GSAS-II's
    "Standard TIF image" reader accepts plain baseline TIFF files.
    """
    values = [(x * 37 + y * 11) % 4096 for y in range(height) for x in range(width)]
    pixels = b"".join(struct.pack("<H", v) for v in values)

    tags = [
        (256, 3, 1, width),      # ImageWidth
        (257, 3, 1, height),     # ImageLength
        (258, 3, 1, 16),         # BitsPerSample
        (259, 3, 1, 1),          # Compression = none
        (262, 3, 1, 1),          # PhotometricInterpretation = BlackIsZero
        (273, 4, 1, 0),          # StripOffsets, patched below
        (277, 3, 1, 1),          # SamplesPerPixel
        (278, 3, 1, height),     # RowsPerStrip
        (279, 4, 1, len(pixels)),  # StripByteCounts
    ]
    ifd_offset = 8
    data_offset = ifd_offset + 2 + len(tags) * 12 + 4
    tags[5] = (273, 4, 1, data_offset)

    header = struct.pack("<2sHI", b"II", 42, ifd_offset)
    body = struct.pack("<H", len(tags))
    for tag, field_type, count, value in tags:
        body += struct.pack("<HHII", tag, field_type, count, value)
    body += struct.pack("<I", 0)

    path.write_bytes(header + body + pixels)
    return path


@pytest.fixture(autouse=True)
def clean_session() -> Iterator[None]:
    """Give every test its own empty server session."""
    from gsas2_mcp_server import state

    state.reset_session()
    yield
    state.reset_session()


@pytest.fixture(scope="session")
def engine_ready() -> dict:
    """Bootstrap GSAS-II once per session and return its capabilities."""
    from gsas2_mcp_server import engine

    return engine.bootstrap()


@pytest.fixture
def testinp() -> pathlib.Path:
    """Directory with the powder pattern, instrument file and CIFs."""
    if not TESTINP.is_dir():
        pytest.skip("tests/testinp is missing from this checkout")
    return TESTINP


@pytest.fixture
def project(tmp_path: pathlib.Path, engine_ready: dict):
    """An open project with one powder histogram already imported."""
    from gsas2_mcp_server import tools_data, tools_project

    gpx_path = tmp_path / "project.gpx"
    created = tools_project.create_project(str(gpx_path))
    assert created["ok"], created

    data = TESTINP / "PBSO4.XRA"
    inst = TESTINP / "INST_XRY.PRM"
    if not (data.is_file() and inst.is_file()):
        pytest.skip("powder test data is missing from this checkout")
    added = tools_data.add_powder_histogram(str(data), iparams=str(inst))
    assert added["ok"], added
    return gpx_path


@pytest.fixture
def linked_project(project):
    """A project whose histogram is linked to a phase.

    GSAS-II addresses variables by index into its phase/histogram/atom tables,
    and those tables are only populated for histograms that a phase uses.  So
    ``':0:Scale'`` cannot be resolved until a phase exists and is linked to the
    data -- this fixture provides that state.
    """
    from gsas2_mcp_server import tools_data

    added = tools_data.add_phase(phasename="PbSO4", histograms=["all"],
                                 cell=[8.48, 5.40, 6.96, 90.0, 90.0, 90.0])
    assert added["ok"], added
    assert added["linked_histograms"], "the phase must be linked to the histogram"
    return project


@pytest.fixture
def tiff_image(tmp_path: pathlib.Path) -> pathlib.Path:
    """A small synthetic detector image for add_image tests."""
    return write_gray_tiff(tmp_path / "synthetic.tif")
