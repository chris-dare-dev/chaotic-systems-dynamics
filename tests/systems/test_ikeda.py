"""Ikeda map tests.

Pinned observables:

- **Constant Jacobian determinant** ``det J = u²`` at every point.
  This is a property of the reduced form ``F = (1, 0) + u R(t) (x, y)`` —
  a uniform-``u`` scaling composed with a state-dependent rotation; the
  ``t(x, y)`` dependence drops out of the determinant. Verify
  numerically by finite differences at a generic point with the
  default ``u = 0.9`` (so ``det = 0.81``).
- **Collapse at u = 0:** with no gain the map becomes ``F(x, y) = (1, 0)``
  identically — the fixed point of the contracting limit.
- **Bounded orbit at default u:** the Ikeda spiral attractor stays in
  a tight box; no iterate diverges over 5000 steps from a generic IC.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.systems import Ikeda
from chaotic_systems.systems.registry import get_map, list_maps


def test_rhs_returns_finite_2vector_at_default_ic() -> None:
    sys = Ikeda()
    out = sys.step(sys.initial_state)
    assert out.shape == (2,)
    assert np.isfinite(out).all()


def test_default_parameter_is_canonical() -> None:
    """Default ``u = 0.9`` — Hammel/Jones/Moloney 1985 strange-attractor value."""
    assert Ikeda().parameters["u"].default == pytest.approx(0.9)


def test_collapse_at_zero_gain() -> None:
    """At u = 0 every iterate lands at (1, 0)."""
    sys = Ikeda()
    for ic in (np.array([0.0, 0.0]), np.array([2.5, -1.7]), np.array([-3.0, 0.4])):
        out = sys.step(ic, u=0.0)
        np.testing.assert_allclose(out, np.array([1.0, 0.0]), atol=1e-12)


def test_jacobian_determinant_equals_u_squared() -> None:
    """``det J = u²`` everywhere — the t(x,y) dependence drops out.

    Derivation: with ``g = x sin t + y cos t``, ``h = x cos t - y sin t``,
    the off-diagonal mixing of ``∂t/∂x`` and ``∂t/∂y`` contributes
    ``x ∂t/∂y - y ∂t/∂x = 0`` (since ``∂t/∂x = 12x/s²``,
    ``∂t/∂y = 12y/s²``). The remaining factor is the bare
    ``u² (cos²t + sin²t) = u²``.
    """
    sys = Ikeda()
    u = sys.parameters["u"].default
    eps = 1e-6
    # Sample several points; the determinant must agree on all of them.
    for base in (
        np.array([0.5, 0.3]),
        np.array([-0.8, 1.2]),
        np.array([2.0, -1.5]),
    ):
        f0 = sys.step(base)
        fx = sys.step(base + np.array([eps, 0.0]))
        fy = sys.step(base + np.array([0.0, eps]))
        jac = np.column_stack([(fx - f0) / eps, (fy - f0) / eps])
        det = float(np.linalg.det(jac))
        assert det == pytest.approx(u * u, abs=1e-4)


def test_orbit_is_bounded_at_default_u() -> None:
    sys = Ikeda()
    traj = sys.iterate(n_steps=5000, y0=np.array([0.1, 0.1]), n_transient=500)
    assert np.isfinite(traj.y).all()
    # Ikeda spiral attractor lives in roughly [-0.5, 2] x [-2, 1] for u=0.9.
    assert np.abs(traj.y).max() < 5.0


def test_registered_as_map() -> None:
    names = [m.name for m in list_maps()]
    assert "Ikeda" in names
    assert get_map("Ikeda").state_dim == 2
