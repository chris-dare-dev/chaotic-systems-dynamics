"""Colormap-registry tests (CSC-009).

Pinned observables:

- Every name from ``available()`` resolves through ``get()`` to a matplotlib
  ``Colormap`` (the anti-inline-``get_cmap`` contract: one lookup point).
- The custom ``conradi`` ramp is black -> #ffe100 (the sourced endpoints from
  Conradi's ``Nice_orbits.ipynb``), with a pure-black low end so zero-count
  cells vanish on a black background.
- ``magma`` / ``inferno`` resolve to the real perceptually-uniform maps and
  also have near-black low ends (Smith & van der Walt 2015).
- Unknown names raise ``KeyError`` rather than silently returning a default.
"""

from __future__ import annotations

import numpy as np
import pytest
from matplotlib.colors import Colormap

from chaotic_systems.visualization import colormaps


def test_available_lists_expected_names() -> None:
    names = colormaps.available()
    assert names[0] == "conradi"  # custom ramp shown first
    assert "magma" in names
    assert "inferno" in names


def test_every_available_name_resolves_to_a_colormap() -> None:
    for name in colormaps.available():
        cmap = colormaps.get(name)
        assert isinstance(cmap, Colormap)


def test_conradi_ramp_endpoints() -> None:
    """conradi(0) is pure black; conradi(1) is #ffe100 (255, 225, 0)."""
    cmap = colormaps.get("conradi")
    low = np.asarray(cmap(0.0))
    high = np.asarray(cmap(1.0))
    # Low end: pure black RGB (alpha 1).
    np.testing.assert_allclose(low[:3], [0.0, 0.0, 0.0], atol=1e-6)
    # High end: #ffe100 -> (1.0, 0.882353, 0.0).
    np.testing.assert_allclose(
        high[:3], [1.0, 0xE1 / 255.0, 0.0], atol=1e-6
    )


def test_conradi_ramp_is_monotone_brightening() -> None:
    """Luminance rises from 0 to 1 along the ramp (a usable density ramp)."""
    cmap = colormaps.get("conradi")
    xs = np.linspace(0.0, 1.0, 16)
    lum = np.array([sum(cmap(x)[:3]) for x in xs])  # crude brightness proxy
    assert np.all(np.diff(lum) >= -1e-9)  # non-decreasing
    assert lum[0] < lum[-1]


@pytest.mark.parametrize("name", ["magma", "inferno"])
def test_builtin_low_end_is_near_black(name: str) -> None:
    cmap = colormaps.get(name)
    low = np.asarray(cmap(0.0))
    assert float(low[:3].max()) < 0.05  # near-black so black bg falls out


def test_unknown_name_raises_keyerror() -> None:
    with pytest.raises(KeyError, match="unknown colormap"):
        colormaps.get("not-a-colormap")
