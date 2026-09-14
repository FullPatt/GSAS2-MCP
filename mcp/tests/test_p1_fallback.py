"""Regression tests for the fork's space-group fallback.

GSAS-II needs the compiled ``pyspg`` extension to interpret space group
symbols.  On a platform without it, ``GSASIIobj.P1SGData`` used to be left
undefined by a bare ``except: pass``, so every ``SetNewPhase`` call later died
with ``NameError: name 'P1SGData' is not defined``.

These tests pin the replacement behaviour:

* ``P 1`` and ``P -1`` resolve without ``pyspg``, and produce space group
  objects identical to the ones a working build produces;
* the hand-written fallback in ``GSASIIobj`` agrees with ``SpcGroup``;
* any other symbol fails with an explanatory ``RuntimeError`` instead of a
  ``NameError``.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("GSASII")

from GSASII import GSASIIobj as G2obj   # noqa: E402
from GSASII import GSASIIspc as G2spc   # noqa: E402


def _normalise(value):
    """Turn numpy containers into plain Python for comparison."""
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    return value


@pytest.mark.parametrize("symbol", ["P 1", "P -1"])
def test_trivial_space_groups_resolve_without_pyspg(symbol: str) -> None:
    """Both trivial space groups are available even with no compiled extension."""
    error, sgdata = G2spc.SpcGroup(symbol)
    assert error == 0
    assert sgdata, "SpcGroup returned an empty space group object"
    assert sgdata["SpGrp"] == symbol
    assert sgdata["SGSys"] == "triclinic"
    assert sgdata["SGLaue"] == "-1"
    assert sgdata["SGLatt"] == "P"
    assert sgdata["SGUniq"] == ""


def test_p1_is_acentric_and_p_minus_1_is_centric() -> None:
    """The inversion flag and the generated operations must agree.

    GSAS-II stores only the acentric operations in ``SGOps`` and generates the
    inverted copies from ``SGInv`` (see ``AllOps`` and ``SGPrint``), so the
    multiplicities are 1 for P 1 and 2 for P -1.
    """
    _, p1 = G2spc.SpcGroup("P 1")
    _, pbar1 = G2spc.SpcGroup("P -1")

    assert p1["SGInv"] is False
    assert pbar1["SGInv"] is True

    assert len(p1["SGOps"]) == 1
    assert len(pbar1["SGOps"]) == 1

    ops_p1 = G2spc.AllOps(p1)[2]
    ops_pbar1 = G2spc.AllOps(pbar1)[2]
    assert len(ops_p1) == 1
    assert len(ops_pbar1) == 2
    assert p1["SGPtGrp"] == "1"
    assert pbar1["SGPtGrp"] == "-1"


def test_object_p1sgdata_matches_spcgroup() -> None:
    """The hand-written P 1 object must not drift from the real one.

    ``GSASIIobj`` builds P 1 by hand when the import order leaves ``GSASIIspc``
    partially initialised; this test is the pin that keeps the two in step.
    """
    assert G2obj.P1SGData is not None, "P1SGData must never be left undefined"
    _, real = G2spc.SpcGroup("P 1")

    hand = G2obj.P1SGData
    assert set(hand) == set(real), "key sets differ"
    for key in real:
        assert _normalise(hand[key]) == _normalise(real[key]), (
            "{} differs: hand={!r} real={!r}".format(key, hand[key], real[key]))


def test_set_new_phase_works_with_the_default_space_group() -> None:
    """SetNewPhase uses P1SGData, so it must not raise NameError."""
    phase = G2obj.SetNewPhase("FallbackTest")
    assert phase["General"]["Name"] == "FallbackTest"
    assert phase["General"]["SGData"]["SpGrp"] == "P 1"


def test_nontrivial_space_group_fails_with_explanation() -> None:
    """Without pyspg, an unsupported symbol must raise RuntimeError, not NameError."""
    if G2spc.pyspg is not None:
        pytest.skip("this build has the compiled pyspg extension; "
                    "the fallback path is not exercised")
    with pytest.raises(RuntimeError) as excinfo:
        G2spc.SpcGroup("P n m a")
    message = str(excinfo.value)
    assert "pyspg" in message
    assert "P n m a" in message


def test_fallback_space_group_object_is_usable() -> None:
    """The P 1 object carries everything downstream code expects."""
    _, sgdata = G2spc.SpcGroup("P 1")
    for key in ("SpGrp", "SGFixed", "SGGray", "SGLaue", "SGInv", "SGLatt",
                "SGUniq", "SGCen", "SGOps", "SGSys", "SGPolax", "SGPtGrp"):
        assert key in sgdata, key

    matrix, translation = sgdata["SGOps"][0]
    assert _normalise(matrix) == [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    assert _normalise(translation) == [0, 0, 0]
    assert _normalise(sgdata["SGCen"]) == [[0, 0, 0]]
