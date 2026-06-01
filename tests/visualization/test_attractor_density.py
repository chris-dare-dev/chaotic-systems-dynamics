"""Tests for the density-accumulation render engine (CSC-002).

Pinned observables:

- ``render`` returns an ``(H, W, 4)`` uint8 RGBA image.
- ``count == 0`` cells map to exact black ``(0, 0, 0, 255)`` (crisp background).
- A fixed seed lattice + params is byte-reproducible across calls.
- All four tone modes produce valid RGBA; ``log`` compresses harder than
  ``linear`` (higher mean brightness on the same count field).
- The numba fast path and the NumPy fallback bin the *same* total mass and
  agree structurally (per-cell exactness is impossible for a chaotic map).
- Bloom only brightens.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.core._numba import NUMBA_AVAILABLE
from chaotic_systems.visualization import attractor_density as ad

# Canonical Conradi regime, verbatim from Nice_orbits.ipynb.
_CANONICAL_A: float = 5.46
_CANONICAL_B: float = 4.55

# Small, fast render parameters for the test suite (the look is not under test,
# the pipeline contracts are). All Conradi iterates stay in the [-1, 1] window.
_KW = dict(n_points=60, n_iter=80, bins=64)


def test_output_shape_and_dtype() -> None:
    rgba = ad.render(_CANONICAL_A, _CANONICAL_B, **_KW)
    assert rgba.shape == (_KW["bins"], _KW["bins"], 4)
    assert rgba.dtype == np.uint8


def test_black_background_for_empty_cells() -> None:
    """Every cell with zero counts colors to exact black (0, 0, 0, 255)."""
    count = ad.accumulate(_CANONICAL_A, _CANONICAL_B, **_KW)
    rgba = ad.render(_CANONICAL_A, _CANONICAL_B, cmap_name="magma", **_KW)
    empty = count == 0
    assert empty.any()  # the attractor does not fill the whole square
    assert np.all(rgba[empty] == (0, 0, 0, 255))


def test_byte_reproducible() -> None:
    """Same lattice + params -> identical image across two calls."""
    first = ad.render(_CANONICAL_A, _CANONICAL_B, tone="log", **_KW)
    second = ad.render(_CANONICAL_A, _CANONICAL_B, tone="log", **_KW)
    assert np.array_equal(first, second)


@pytest.mark.parametrize("tone", ["eq_hist", "log", "cbrt", "linear"])
def test_all_tone_modes_produce_valid_rgba(tone: str) -> None:
    rgba = ad.render(_CANONICAL_A, _CANONICAL_B, tone=tone, **_KW)
    assert rgba.shape == (_KW["bins"], _KW["bins"], 4)
    assert rgba.dtype == np.uint8
    # Alpha channel is fully opaque everywhere.
    assert np.all(rgba[..., 3] == 255)
    # A non-degenerate image: some lit pixels, some black background.
    lit = rgba[..., :3].sum(axis=2) > 0
    assert lit.any() and not lit.all()


def test_log_tone_is_brighter_than_linear() -> None:
    """The compressive log transfer lifts faint cells above the linear map."""
    count = ad.accumulate(_CANONICAL_A, _CANONICAL_B, **_KW)
    log_b = ad.tone_map(count, "log")
    linear_b = ad.tone_map(count, "linear")
    assert log_b.mean() > linear_b.mean()


def test_tone_map_zero_count_is_black() -> None:
    """Empty cells map to brightness 0 in every mode."""
    count = np.zeros((8, 8), dtype=np.float64)
    count[3, 4] = 10.0
    for tone in ("eq_hist", "log", "cbrt", "linear"):
        bright = ad.tone_map(count, tone)  # type: ignore[arg-type]
        assert bright[count == 0].max() == 0.0
        assert bright[3, 4] > 0.0


def test_unknown_tone_mode_raises() -> None:
    count = np.ones((4, 4), dtype=np.float64)
    with pytest.raises(ValueError, match="unknown tone mode"):
        ad.tone_map(count, "sigmoid")  # type: ignore[arg-type]


def test_count_max_override_caps_brightness() -> None:
    """A large fixed count_max darkens the log image vs the per-frame default."""
    count = ad.accumulate(_CANONICAL_A, _CANONICAL_B, **_KW)
    adaptive = ad.tone_map(count, "log")
    capped = ad.tone_map(count, "log", count_max=count.max() * 100.0)
    assert capped.mean() < adaptive.mean()


@pytest.mark.skipif(not NUMBA_AVAILABLE, reason="numba [performance] extra absent")
def test_numba_and_numpy_paths_agree() -> None:
    """The JIT and NumPy accumulations bin equal mass and agree structurally.

    The Conradi map is chaotic, so numba/numpy sin/cos differ by ~1 ULP and the
    per-seed trajectories diverge after a few dozen steps. Per-cell equality is
    therefore unattainable; the invariants that DO hold are (1) the total binned
    mass (every iterate of the bounded map lands in-window) and (2) strong
    structural correlation between the two density fields.
    """
    jit = ad.accumulate(_CANONICAL_A, _CANONICAL_B, use_numba=True, **_KW)
    npy = ad.accumulate(_CANONICAL_A, _CANONICAL_B, use_numba=False, **_KW)
    expected_mass = float(_KW["n_points"] ** 2 * _KW["n_iter"])
    assert jit.sum() == pytest.approx(expected_mass)
    assert npy.sum() == pytest.approx(expected_mass)
    corr = np.corrcoef(jit.ravel(), npy.ravel())[0, 1]
    assert corr > 0.8


def test_bloom_increases_mean_brightness() -> None:
    """Bloom adds a halo around hot cores -> strictly higher mean brightness."""
    bright = np.zeros((64, 64), dtype=np.float64)
    bright[30:34, 30:34] = 1.0  # a hot core above the bloom threshold
    bloomed = ad.apply_bloom(bright)
    assert bloomed.mean() > bright.mean()
    assert bloomed.max() <= 1.0  # screen blend stays in range


def test_render_bloom_does_not_darken() -> None:
    no_bloom = ad.render(_CANONICAL_A, _CANONICAL_B, tone="log", bloom=False, **_KW)
    with_bloom = ad.render(_CANONICAL_A, _CANONICAL_B, tone="log", bloom=True, **_KW)
    assert with_bloom[..., :3].mean() >= no_bloom[..., :3].mean()
