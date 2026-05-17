"""Chirikov standard map tests.

Pinned observables:

- **Area preservation:** the Jacobian determinant is identically ``1``
  for every ``(theta, p)`` and every ``K``. Pick a point away from the
  ``mod 2π`` boundary and verify by finite differences that
  ``|det J - 1| < 1e-6``.
- **Wrapping:** every coordinate of every iterate is in ``[-π, π)``.
- **Integrable backbone at K = 0:** with ``K = 0`` the map reduces to
  rigid rotation ``(theta, p) -> (theta + p, p)``, so ``p`` is conserved
  exactly along the orbit.
- **Critical-K default:** the registered default sits at the
  golden-mean KAM-breakup value ``K_c ≈ 0.971635`` (Greene 1979).
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.systems import StandardMap
from chaotic_systems.systems.registry import get_map, list_maps


def test_rhs_returns_finite_2vector_at_default_ic() -> None:
    sys = StandardMap()
    out = sys.step(sys.initial_state)
    assert out.shape == (2,)
    assert np.isfinite(out).all()


def test_default_K_is_chirikov_critical() -> None:
    sys = StandardMap()
    assert sys.parameters["K"].default == pytest.approx(0.971635, abs=1e-6)


def test_zero_K_conserves_momentum_exactly() -> None:
    """``p`` is integrable for K = 0 — the orbit is a rigid rotation."""
    sys = StandardMap()
    p0 = 0.7
    traj = sys.iterate(
        n_steps=200, y0=np.array([0.1, p0]), params={"K": 0.0}
    )
    np.testing.assert_allclose(traj.y[:, 1], p0, atol=1e-12)


def test_jacobian_determinant_is_one_away_from_mod_boundary() -> None:
    """Symplectic / area-preserving for every K and every interior point."""
    sys = StandardMap()
    eps = 1e-6
    # Stay well inside (-pi, pi) on both axes so the mod wrap stays linear.
    for base in (
        np.array([0.4, 0.3]),
        np.array([-1.2, 0.8]),
        np.array([1.5, -0.6]),
    ):
        f0 = sys.step(base)
        ftheta = sys.step(base + np.array([eps, 0.0]))
        fp = sys.step(base + np.array([0.0, eps]))
        jac = np.column_stack([(ftheta - f0) / eps, (fp - f0) / eps])
        det = float(np.linalg.det(jac))
        assert det == pytest.approx(1.0, abs=1e-6)


def test_iterates_stay_inside_mod_2pi_box() -> None:
    """Both ``theta`` and ``p`` are wrapped into ``[-pi, pi)``."""
    sys = StandardMap()
    traj = sys.iterate(
        n_steps=5000, y0=np.array([0.5, 0.5]), params={"K": 2.5}
    )
    assert traj.y[:, 0].min() >= -np.pi - 1e-12
    assert traj.y[:, 0].max() < np.pi + 1e-12
    assert traj.y[:, 1].min() >= -np.pi - 1e-12
    assert traj.y[:, 1].max() < np.pi + 1e-12


def test_registered_as_map() -> None:
    names = [m.name for m in list_maps()]
    assert "StandardMap" in names
    assert get_map("StandardMap").state_dim == 2
