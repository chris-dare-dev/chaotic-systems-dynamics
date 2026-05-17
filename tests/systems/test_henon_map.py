"""Hénon map tests.

Pinned observables (from Hénon 1976):

- **Area contraction factor:** the Jacobian determinant is identically
  ``-b`` — measure it by finite differences at a generic point.
- **Strange attractor bounds:** at ``(a, b) = (1.4, 0.3)``, the attractor
  is contained in ``x ∈ [-1.34, 1.27]``, ``y ∈ [-0.4, 0.41]`` (Hénon
  1976, table 2). After a long transient the trajectory must stay in
  ``|x| < 1.5``, ``|y| < 0.5``.
- **Fixed points** of the map satisfy ``a x^2 + (1 - b) x - 1 = 0`` with
  ``y = b x``. For ``(a, b) = (1.4, 0.3)`` the two roots are
  ``x = (-(1-b) ± sqrt((1-b)^2 + 4a)) / (2a)``; the positive root is
  ``x* ≈ 0.6314``, ``y* ≈ 0.1894``.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.systems import HenonMap
from chaotic_systems.systems.registry import get_map, list_maps


def test_rhs_returns_finite_2vector_at_default_ic() -> None:
    sys = HenonMap()
    out = sys.step(sys.initial_state)
    assert out.shape == (2,)
    assert np.isfinite(out).all()


def test_default_parameters_are_canonical() -> None:
    """Hénon 1976 strange-attractor parameters."""
    sys = HenonMap()
    assert sys.parameters["a"].default == pytest.approx(1.4)
    assert sys.parameters["b"].default == pytest.approx(0.3)


def test_jacobian_determinant_equals_minus_b() -> None:
    """``det J = -b`` for the Hénon map — measure by finite differences."""
    sys = HenonMap()
    b = sys.parameters["b"].default
    eps = 1e-6
    # Pick a generic point well inside the attractor.
    base = np.array([0.5, 0.1], dtype=np.float64)
    f0 = sys.step(base)
    fx = sys.step(base + np.array([eps, 0.0]))
    fy = sys.step(base + np.array([0.0, eps]))
    jac = np.column_stack([(fx - f0) / eps, (fy - f0) / eps])
    det = float(np.linalg.det(jac))
    assert det == pytest.approx(-b, abs=1e-6)


def test_unstable_fixed_point_solves_quadratic() -> None:
    """``F(x*, b x*) = (x*, b x*)`` gives the unstable saddle on the attractor."""
    sys = HenonMap()
    a = sys.parameters["a"].default
    b = sys.parameters["b"].default
    discriminant = np.sqrt((1.0 - b) ** 2 + 4.0 * a)
    x_star = (-(1.0 - b) + discriminant) / (2.0 * a)
    y_star = b * x_star
    out = sys.step(np.array([x_star, y_star]))
    np.testing.assert_allclose(out, np.array([x_star, y_star]), atol=1e-12)


def test_attractor_is_bounded_after_transient() -> None:
    """The strange attractor stays in a tight box (Hénon 1976 table 2)."""
    sys = HenonMap()
    traj = sys.iterate(n_steps=10_000, y0=np.array([0.1, 0.1]), n_transient=500)
    xs = traj.y[:, 0]
    ys = traj.y[:, 1]
    assert np.isfinite(traj.y).all()
    # Loose bounding box — Hénon 1976 reports ~[-1.34, 1.27] x [-0.4, 0.41].
    assert np.abs(xs).max() < 1.5
    assert np.abs(ys).max() < 0.5


def test_registered_as_map() -> None:
    names = [m.name for m in list_maps()]
    assert "HenonMap" in names
    assert get_map("HenonMap").state_dim == 2
