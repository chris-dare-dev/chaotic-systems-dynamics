"""Tests for the closed (a, b) parameter loop + frame precompute (CSC-005).

Pinned observables:

- **Seamlessness** (the proposal's observable): ``param_loop(0) == param_loop(1)``
  to machine precision, so the rendered loop has no seam.
- Vectorized evaluation matches scalar; outputs are wrapped into ``[0, 2*pi)``.
- ``precompute_loop_frames`` returns ``n_frames`` RGBA frames, the (a, b) of
  each frame, and a **single** fixed ``count_max`` — and each frame is exactly
  what :func:`attractor_density.render` produces at that ``count_max`` (the
  fixed-scale, no-flicker contract from CSC-002).
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.visualization import attractor_density
from chaotic_systems.visualization import param_path as pp

_TWO_PI = 2.0 * np.pi


def test_loop_is_seamless() -> None:
    """param_loop(0) and param_loop(1) coincide to machine precision."""
    a0, b0 = pp.param_loop(0.0)
    a1, b1 = pp.param_loop(1.0)
    assert float(a0) == pytest.approx(float(a1), abs=1e-12)
    assert float(b0) == pytest.approx(float(b1), abs=1e-12)


def test_vectorized_matches_scalar() -> None:
    ts = np.linspace(0.0, 1.0, 9, endpoint=False)
    a_vec, b_vec = pp.param_loop(ts)
    for i, t in enumerate(ts):
        a_s, b_s = pp.param_loop(float(t))
        assert float(a_vec[i]) == pytest.approx(float(a_s), abs=1e-12)
        assert float(b_vec[i]) == pytest.approx(float(b_s), abs=1e-12)


def test_values_wrapped_into_range() -> None:
    ts = np.linspace(0.0, 1.0, 200, endpoint=False)
    a, b = pp.param_loop(ts)
    assert float(np.min(a)) >= 0.0
    assert float(np.max(a)) < _TWO_PI
    assert float(np.min(b)) >= 0.0
    assert float(np.max(b)) < _TWO_PI


def test_precompute_frame_count_and_shapes() -> None:
    frames, ab, count_max = pp.precompute_loop_frames(
        6, n_points=50, n_iter=50, bins=48, prescan_frames=3
    )
    assert len(frames) == 6
    assert len(ab) == 6
    assert all(f.shape == (48, 48, 4) and f.dtype == np.uint8 for f in frames)
    assert isinstance(count_max, float)
    assert count_max >= 1.0


def test_precompute_uses_fixed_count_max_for_every_frame() -> None:
    """Each frame equals render(...) at the single shared count_max (no flicker)."""
    kw = dict(n_points=50, n_iter=50, bins=48)
    frames, ab, count_max = pp.precompute_loop_frames(
        5, prescan_frames=2, **kw
    )
    for i, (a, b) in enumerate(ab):
        expected = attractor_density.render(
            a,
            b,
            tone="log",
            gamma=attractor_density.DEFAULT_GAMMA,
            cmap_name="magma",
            bloom=False,
            count_max=count_max,
            **kw,
        )
        assert np.array_equal(frames[i], expected)


def test_path_actually_moves() -> None:
    frames, ab, _ = pp.precompute_loop_frames(
        6, n_points=40, n_iter=40, bins=32, prescan_frames=2
    )
    # The (a, b) of frame 0 and a mid frame differ -> the loop sweeps.
    assert ab[0] != ab[3]


def test_invalid_n_frames_raises() -> None:
    with pytest.raises(ValueError, match="n_frames must be"):
        pp.precompute_loop_frames(0)
