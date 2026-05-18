"""Tests for the bifurcation-diagram compute.

Reference observables drawn directly from Strogatz §10.3-10.4:

- **Fixed-point regime** at ``r = 2.5`` on the logistic map: every
  sampled iterate equals the analytic fixed point ``1 - 1/r = 0.6``
  to machine precision.
- **Period-2 regime** at ``r = 3.2``: only two unique values appear,
  ``((r+1) ± sqrt((r-3)(r+1))) / (2r) ≈ {0.5130, 0.7995}``.
- **Period-4 regime** at ``r = 3.5``: four unique values appear.
- **Period-3 window** at ``r = 3.835``: three unique values (the
  stable period-3 orbit Strogatz Fig 10.4.1 shows).
- **Chaotic regime** at ``r = 3.9``: many distinct values (>50 even
  at ``n_record = 100``).

These pin the bifurcation routine to the same numerics the
literature uses.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.core import bifurcation_diagram
from chaotic_systems.core.bifurcation import (
    DEFAULT_N_RECORD,
    DEFAULT_N_TRANSIENT,
    BifurcationDiagram,
    as_scatter,
)
from chaotic_systems.systems import HenonMap, Logistic


def _unique_within(arr: np.ndarray, tol: float) -> np.ndarray:
    """Return the unique values of ``arr`` up to a quantization tolerance."""
    rounded = np.round(arr / tol) * tol
    return np.unique(rounded)


def test_diagram_shape_and_dataclass_invariants() -> None:
    sys = Logistic()
    rs = np.linspace(2.5, 4.0, 10)
    diag = bifurcation_diagram(sys, "r", rs, n_record=30, n_transient=100)
    assert isinstance(diag, BifurcationDiagram)
    assert diag.system_name == "Logistic"
    assert diag.param_name == "r"
    assert diag.n_values == 10
    assert diag.n_record == 30
    assert diag.state_dim == 1
    assert diag.samples.shape == (10, 30, 1)
    np.testing.assert_allclose(diag.param_values, rs)


def test_fixed_point_below_three() -> None:
    """At r=2.5 the orbit is the stable fixed point 1 - 1/r = 0.6."""
    sys = Logistic()
    diag = bifurcation_diagram(
        sys, "r", np.array([2.5]), n_record=50, n_transient=500
    )
    assert diag.samples.shape == (1, 50, 1)
    np.testing.assert_allclose(diag.samples[0, :, 0], 0.6, atol=1e-10)


def test_period_2_at_r_3_2() -> None:
    """Strogatz eq. 10.3.3 cycle points."""
    r = 3.2
    sys = Logistic()
    diag = bifurcation_diagram(
        sys, "r", np.array([r]), n_record=200, n_transient=3000
    )
    unique = _unique_within(diag.samples[0, :, 0], 1e-6)
    assert unique.shape == (2,), f"expected 2 cycle points, got {unique!r}"
    disc = np.sqrt((r - 3.0) * (r + 1.0))
    expected = np.sort(
        [((r + 1.0) - disc) / (2.0 * r), ((r + 1.0) + disc) / (2.0 * r)]
    )
    np.testing.assert_allclose(unique, expected, atol=1e-6)


def test_period_4_at_r_3_5() -> None:
    sys = Logistic()
    diag = bifurcation_diagram(
        sys, "r", np.array([3.5]), n_record=400, n_transient=5000
    )
    unique = _unique_within(diag.samples[0, :, 0], 1e-4)
    assert unique.shape == (4,), f"expected 4 cycle points, got {unique!r}"


def test_period_3_window_at_r_3_835() -> None:
    """Strogatz Fig 10.4.1 — the period-3 window born at r ≈ 1 + sqrt(8)."""
    sys = Logistic()
    diag = bifurcation_diagram(
        sys, "r", np.array([3.835]), n_record=300, n_transient=5000
    )
    unique = _unique_within(diag.samples[0, :, 0], 1e-4)
    assert unique.shape == (3,), f"expected 3 cycle points, got {unique!r}"


def test_chaotic_regime_has_many_unique_values() -> None:
    """At r=3.9 the orbit is chaotic (Lyapunov > 0); recorded values cover
    a continuum, so the number of unique iterates should be large."""
    sys = Logistic()
    diag = bifurcation_diagram(
        sys, "r", np.array([3.9]), n_record=100, n_transient=2000
    )
    unique = _unique_within(diag.samples[0, :, 0], 1e-3)
    assert unique.shape[0] > 50


def test_as_scatter_flattens_correctly() -> None:
    sys = Logistic()
    rs = np.linspace(3.0, 4.0, 4)
    diag = bifurcation_diagram(sys, "r", rs, n_record=10, n_transient=50)
    xs, ys = as_scatter(diag, projection=0)
    assert xs.shape == (40,)
    assert ys.shape == (40,)
    # Every parameter value should appear exactly n_record times.
    counts = np.bincount(np.searchsorted(rs, xs))
    np.testing.assert_array_equal(counts, np.full(4, 10))


def test_as_scatter_rejects_bad_projection() -> None:
    sys = Logistic()
    diag = bifurcation_diagram(sys, "r", np.array([3.0]), n_record=5, n_transient=10)
    with pytest.raises(ValueError, match="projection axis"):
        as_scatter(diag, projection=5)


def test_henon_diagram_uses_projection_axis() -> None:
    """A 2D map: pick projection=1 to plot the y-component instead of x."""
    sys = HenonMap()
    diag = bifurcation_diagram(
        sys, "a", np.linspace(1.0, 1.4, 5), n_record=20, n_transient=200
    )
    assert diag.state_dim == 2
    assert diag.samples.shape == (5, 20, 2)
    xs0, ys0 = as_scatter(diag, projection=0)
    xs1, ys1 = as_scatter(diag, projection=1)
    np.testing.assert_array_equal(xs0, xs1)
    # The two projections must not be identical (different state components).
    assert not np.allclose(ys0, ys1)


def test_diagram_rejects_unknown_param() -> None:
    sys = Logistic()
    with pytest.raises(KeyError, match="unknown parameter"):
        bifurcation_diagram(sys, "bogus", np.array([1.0, 2.0]))


def test_diagram_rejects_continuous_system() -> None:
    """Continuous DynamicalSystems aren't supported by v1 (Poincaré path TBD)."""
    from chaotic_systems.systems import Lorenz

    with pytest.raises(TypeError, match="DiscreteSystem only"):
        bifurcation_diagram(Lorenz(), "rho", np.linspace(20.0, 30.0, 5))


def test_diagram_validates_param_values_shape() -> None:
    sys = Logistic()
    with pytest.raises(ValueError, match="param_values must be 1-D"):
        bifurcation_diagram(sys, "r", np.zeros((2, 2)))


def test_diagram_validates_n_record_and_transient() -> None:
    sys = Logistic()
    rs = np.array([3.5])
    with pytest.raises(ValueError, match="n_record must be >= 1"):
        bifurcation_diagram(sys, "r", rs, n_record=0)
    with pytest.raises(ValueError, match="n_transient must be >= 0"):
        bifurcation_diagram(sys, "r", rs, n_transient=-1)


def test_diagram_seed_y0_validation() -> None:
    sys = Logistic()
    with pytest.raises(ValueError, match="expected"):
        bifurcation_diagram(sys, "r", np.array([3.5]), y0=np.zeros(3))
    with pytest.raises(ValueError, match="non-finite"):
        bifurcation_diagram(sys, "r", np.array([3.5]), y0=np.array([np.nan]))


def test_fixed_params_overrides_default() -> None:
    """When the swept param is shadowed in ``fixed_params`` the sweep value wins."""
    sys = HenonMap()
    diag = bifurcation_diagram(
        sys,
        "a",
        np.linspace(1.0, 1.4, 3),
        n_record=10,
        n_transient=50,
        fixed_params={"a": 999.0, "b": 0.3},  # 'a' override is ignored, 'b' isn't
    )
    assert diag.fixed_params["b"] == pytest.approx(0.3)


def test_default_constants_match_documented_values() -> None:
    """Document the default knobs in one place; this test pins them."""
    assert DEFAULT_N_RECORD == 200
    assert DEFAULT_N_TRANSIENT == 1000
