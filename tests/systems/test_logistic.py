"""Logistic map tests.

Numerical observables pinned:

- **Attracting fixed point** at ``r = 2.7``: ``x* = 1 - 1/r ≈ 0.62963``
  (Strogatz §10.2). Iterating from any seed in ``(0, 1)`` past the
  transient must converge to this value to machine precision.
- **Period-2 orbit** at ``r = 3.2``: the two stable cycle points are
  ``x± = ((r+1) ± sqrt((r-3)(r+1))) / (2r)`` (Strogatz eq. 10.3.3).
  For ``r = 3.2`` this gives ``x± ≈ {0.5130, 0.7995}``.
- **Boundedness in [0, 1]** at the canonical chaotic default ``r = 3.9``.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.systems import Logistic
from chaotic_systems.systems.registry import get_map, list_maps


def test_rhs_returns_finite_scalar_at_default_ic() -> None:
    sys = Logistic()
    out = sys.step(sys.initial_state)
    assert out.shape == (1,)
    assert np.isfinite(out).all()


def test_default_parameter_is_in_chaotic_regime() -> None:
    sys = Logistic()
    # r = 3.9 sits past the period-3 window at 3.828 and well past
    # Feigenbaum r_inf ≈ 3.5699.
    assert sys.parameters["r"].default == pytest.approx(3.9)


def test_kind_attribute_is_map() -> None:
    assert Logistic().kind == "map"


def test_fixed_point_at_r_below_three() -> None:
    """For 1 < r < 3 the unique stable fixed point is 1 - 1/r."""
    sys = Logistic()
    traj = sys.iterate(
        n_steps=1, y0=np.array([0.2]), params={"r": 2.7}, n_transient=500
    )
    expected = 1.0 - 1.0 / 2.7
    np.testing.assert_allclose(traj.y[0, 0], expected, atol=1e-10)


def test_period_2_orbit_at_r_3_2() -> None:
    """Strogatz eq. 10.3.3: x± = ((r+1) ± sqrt((r-3)(r+1))) / (2r).

    For r = 3.2 the orbit alternates between {0.5130..., 0.7995...}.
    """
    r = 3.2
    sys = Logistic()
    traj = sys.iterate(
        n_steps=20, y0=np.array([0.1]), params={"r": r}, n_transient=2000
    )
    samples = np.sort(np.unique(np.round(traj.y[:, 0], 6)))
    discriminant = np.sqrt((r - 3.0) * (r + 1.0))
    x_plus = ((r + 1.0) + discriminant) / (2.0 * r)
    x_minus = ((r + 1.0) - discriminant) / (2.0 * r)
    expected = np.sort([x_minus, x_plus])
    assert samples.shape == (2,), f"expected 2 cycle points, got {samples!r}"
    np.testing.assert_allclose(samples, expected, atol=1e-6)


def test_chaotic_orbit_stays_in_unit_interval() -> None:
    sys = Logistic()
    traj = sys.iterate(n_steps=10_000, y0=np.array([0.123]), n_transient=200)
    assert np.isfinite(traj.y).all()
    assert traj.y.min() >= 0.0
    assert traj.y.max() <= 1.0


def test_registered_as_map() -> None:
    names = [m.name for m in list_maps()]
    assert "Logistic" in names
    assert get_map("Logistic").state_dim == 1
