"""Tests for the Clifford attractor map (CSC-008).

Pinned observables:

- Constructs, is registered as a map, and steps to finite values.
- Bounded to the (c, d)-derived box ``[-(1+|c|), 1+|c|] x [-(1+|d|), 1+|d|]``
  (the sin/cos form cannot diverge) -- so clifford_extent is exact.
- The analytic Jacobian matches a central finite-difference Jacobian.
- It renders through the shared attractor_density pipeline (the proposal's
  observable: "Clifford renders through the same attractor_density path and
  produces its known multi-lobe figure at the Bourke reference parameters").
- The default Bourke parameters are chaotic (lambda_1 > 0).
"""

from __future__ import annotations

import numpy as np

from chaotic_systems.core.lyapunov import largest_lyapunov_discrete_system
from chaotic_systems.systems.clifford import (
    CliffordMap,
    clifford_extent,
    clifford_map,
    make_clifford_map_fn,
)
from chaotic_systems.systems.registry import get_map, list_map_names
from chaotic_systems.visualization import attractor_density as ad

_A, _B, _C, _D = -1.4, 1.6, 1.0, 0.7  # Bourke's default set


def test_constructs_and_steps_finite() -> None:
    m = CliffordMap()
    assert m.name == "CliffordMap"
    assert m.state_dim == 2
    nxt = m.step(m.initial_state)
    assert nxt.shape == (2,)
    assert np.all(np.isfinite(nxt))


def test_registered_as_map() -> None:
    assert "CliffordMap" in list_map_names()
    assert get_map("CliffordMap").name == "CliffordMap"


def test_extent_formula() -> None:
    assert clifford_extent(_C, _D) == (
        -(1.0 + abs(_C)),
        1.0 + abs(_C),
        -(1.0 + abs(_D)),
        1.0 + abs(_D),
    )


def test_bounded_to_cd_box() -> None:
    """Every iterate of a seed grid stays within the (c, d) bounding box."""
    xmin, xmax, ymin, ymax = clifford_extent(_C, _D)
    lin = np.linspace(-2.0, 2.0, 40)
    gx, gy = np.meshgrid(lin, lin)
    x, y = gx.ravel(), gy.ravel()
    for _ in range(200):
        x, y = clifford_map(x, y, _A, _B, _C, _D)
    tol = 1e-9
    assert x.min() >= xmin - tol and x.max() <= xmax + tol
    assert y.min() >= ymin - tol and y.max() <= ymax + tol


def test_jacobian_matches_finite_difference() -> None:
    m = CliffordMap()
    rng = np.random.default_rng(0)
    eps = 1e-7
    for _ in range(5):
        y = rng.uniform(-1.5, 1.5, size=2)
        analytic = m.jacobian(y)
        fd = np.empty((2, 2))
        for i in range(2):
            e = np.zeros(2)
            e[i] = eps
            fd[:, i] = (m.step(y + e) - m.step(y - e)) / (2.0 * eps)
        np.testing.assert_allclose(analytic, fd, atol=1e-6)


def test_make_clifford_map_fn_matches_full_map() -> None:
    map_fn = make_clifford_map_fn(_C, _D)
    x = np.array([0.2, -0.5, 0.9])
    y = np.array([-0.3, 0.7, 0.1])
    fx, fy = map_fn(x, y, _A, _B)
    gx, gy = clifford_map(x, y, _A, _B, _C, _D)
    np.testing.assert_array_equal(fx, gx)
    np.testing.assert_array_equal(fy, gy)


def test_renders_through_attractor_density() -> None:
    """The shared density pipeline produces a non-trivial Clifford image."""
    rgba = ad.render(
        _A,
        _B,
        map_fn=make_clifford_map_fn(_C, _D),
        extent=clifford_extent(_C, _D),
        n_points=100,
        n_iter=100,
        bins=160,
        tone="log",
    )
    assert rgba.shape == (160, 160, 4)
    assert rgba.dtype == np.uint8
    lit = np.any(rgba[..., :3] > 0, axis=2)
    assert lit.any() and not lit.all()  # a real figure on a black background


def test_default_params_are_chaotic() -> None:
    """Bourke's default (-1.4, 1.6, 1.0, 0.7) has a positive largest exponent."""
    lle = largest_lyapunov_discrete_system(
        CliffordMap(), n=40_000, n_transient=2_000
    )
    assert lle > 0.0
