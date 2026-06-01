"""ConradiMap tests.

Pinned observables (from Conradi's ``Nice_orbits.ipynb`` + the derived math in
``.claude/notes/conradi-analysis/math-parameterization.md``):

- **Automatic boundedness:** sin / cos => every iterate after the first lives in
  ``[-1, 1] x [-1, 1]``. This is the map's defining structural property and the
  reason it can never diverge.
- **Analytic Jacobian:** with ``u = x^2 - y^2 + a``, ``v = 2xy + b``,
  ``J = [[2x cos u, -2y cos u], [-2y sin v, -2x sin v]]``. Must match a
  finite-difference Jacobian to ~1e-6 at a generic point.
- **det J = -4 (x^2 + y^2) cos u sin v** (dissipative folding) — a direct
  consequence of the analytic J, checked against finite differences.
- **Canonical parameters** ``(a, b) = (5.46, 4.55)`` taken verbatim from the
  source notebook.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.systems import ConradiMap
from chaotic_systems.systems.registry import get_map, list_maps


def test_step_returns_finite_2vector_at_default_ic() -> None:
    sys = ConradiMap()
    out = sys.step(sys.initial_state)
    assert out.shape == (2,)
    assert np.isfinite(out).all()


def test_default_parameters_are_canonical() -> None:
    """Conradi ``Nice_orbits.ipynb`` parameters."""
    sys = ConradiMap()
    assert sys.parameters["a"].default == pytest.approx(5.46)
    assert sys.parameters["b"].default == pytest.approx(4.55)


def test_iterate_is_bounded_in_unit_square() -> None:
    """sin / cos => every post-first iterate is confined to [-1, 1]^2.

    The defining property: this map cannot diverge. Iterate from a
    deliberately out-of-range seed and from the default seed; after a single
    step everything must be inside the closed unit square (small fp slack).
    """
    sys = ConradiMap()
    for y0 in (np.array([0.1, 0.1]), np.array([5.0, -3.0])):
        traj = sys.iterate(n_steps=5_000, y0=y0, n_transient=10)
        assert np.isfinite(traj.y).all()
        assert traj.y.min() >= -1.0 - 1e-12
        assert traj.y.max() <= 1.0 + 1e-12


def test_analytic_jacobian_matches_finite_difference() -> None:
    """Analytic ``jacobian()`` agrees with a central finite-difference J."""
    sys = ConradiMap()
    eps = 1e-6
    rng = np.random.default_rng(0)
    for _ in range(8):
        # Generic points inside the attractor's [-1, 1]^2 domain.
        base = rng.uniform(-1.0, 1.0, size=2)
        fx = (sys.step(base + [eps, 0.0]) - sys.step(base - [eps, 0.0])) / (2 * eps)
        fy = (sys.step(base + [0.0, eps]) - sys.step(base - [0.0, eps])) / (2 * eps)
        fd = np.column_stack([fx, fy])
        ana = sys.jacobian(base)
        np.testing.assert_allclose(ana, fd, atol=1e-6, rtol=1e-5)


def test_jacobian_determinant_formula() -> None:
    """``det J = -4 (x^2 + y^2) cos(u) sin(v)`` with u, v the channel args."""
    sys = ConradiMap()
    a = sys.parameters["a"].default
    b = sys.parameters["b"].default
    x, y = 0.37, -0.52
    u = x * x - y * y + a
    v = 2.0 * x * y + b
    expected = -4.0 * (x * x + y * y) * np.cos(u) * np.sin(v)
    det = float(np.linalg.det(sys.jacobian(np.array([x, y]))))
    assert det == pytest.approx(expected, abs=1e-12)


def test_jacobian_respects_param_overrides() -> None:
    """Passing a/b overrides changes the Jacobian (it is not hard-wired to defaults)."""
    sys = ConradiMap()
    base = np.array([0.3, 0.4])
    j_default = sys.jacobian(base)
    j_override = sys.jacobian(base, a=1.7, b=2.3)
    assert not np.allclose(j_default, j_override)


def test_registered_as_map() -> None:
    names = [m.name for m in list_maps()]
    assert "ConradiMap" in names
    m = get_map("ConradiMap")
    assert m.state_dim == 2
    assert m.kind == "map"
