"""Tests for the discrete-map largest Lyapunov estimator (CSC-003).

``largest_lyapunov_discrete`` is purely additive alongside the existing
``solve_ivp``-based ODE estimators (tested in ``tests/core/test_kaplan_yorke.py``),
which it does not touch.

Regression anchors from the literature:

- Henon map at ``(a, b) = (1.4, 0.3)``: lambda_1 ~ 0.419 (Henon 1976).
- Logistic map at ``r = 4``: lambda_1 = ln 2 exactly.
- A linear contracting map ``x -> c x`` (``|c| < 1``): lambda_1 = ln|c| < 0,
  exercising the stable/non-chaotic branch.
- The Conradi map: both branches. At its *art* parameters ``(5.46, 4.55)`` a
  single orbit collapses to a stable cycle (lambda_1 <= 0) -- the density art
  is transient lattice flow, not a chaotic attractor -- while a genuinely
  chaotic regime ``(3.9, 4.6)`` gives lambda_1 > 0. Both were confirmed
  numerically to be IC-independent (the estimate is the same from every seed).
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.core.lyapunov import (
    largest_lyapunov_discrete,
    largest_lyapunov_discrete_system,
)
from chaotic_systems.systems.conradi import ConradiMap
from chaotic_systems.systems.henon_map import HenonMap
from chaotic_systems.systems.logistic import Logistic


def test_henon_largest_lyapunov_matches_literature() -> None:
    """Henon at (1.4, 0.3): lambda_1 ~ 0.419 (the canonical regression anchor)."""
    a, b = 1.4, 0.3

    def step(y: np.ndarray) -> np.ndarray:
        return np.array([1.0 - a * y[0] ** 2 + y[1], b * y[0]], dtype=np.float64)

    def jac(y: np.ndarray) -> np.ndarray:
        return np.array([[-2.0 * a * y[0], 1.0], [b, 0.0]], dtype=np.float64)

    lle = largest_lyapunov_discrete(
        step, jac, np.array([0.1, 0.1]), n=40_000, n_transient=2_000
    )
    assert lle == pytest.approx(0.419, abs=0.01)


def test_henon_via_system_step_matches() -> None:
    """The same anchor using HenonMap.step (the public discrete hook)."""
    a, b = 1.4, 0.3
    m = HenonMap()

    def jac(y: np.ndarray) -> np.ndarray:
        return np.array([[-2.0 * a * y[0], 1.0], [b, 0.0]], dtype=np.float64)

    lle = largest_lyapunov_discrete(
        lambda y: m.step(y), jac, np.array([0.1, 0.1]), n=40_000, n_transient=2_000
    )
    assert lle == pytest.approx(0.419, abs=0.02)


def test_logistic_r4_is_ln2() -> None:
    """Logistic at r = 4: lambda_1 = ln 2 (exact for the fully-developed map)."""
    r = 4.0
    m = Logistic()

    def jac(y: np.ndarray) -> np.ndarray:
        return np.array([[r * (1.0 - 2.0 * y[0])]], dtype=np.float64)

    lle = largest_lyapunov_discrete(
        lambda y: m.step(y, r=r),
        jac,
        np.array([0.123]),
        n=60_000,
        n_transient=2_000,
    )
    assert lle == pytest.approx(np.log(2.0), abs=0.01)


def test_contracting_linear_map_is_negative() -> None:
    """x -> c x with |c| < 1: lambda_1 = ln|c| < 0 (stable branch)."""
    c = 0.5

    def step(y: np.ndarray) -> np.ndarray:
        return c * y

    def jac(y: np.ndarray) -> np.ndarray:
        return np.array([[c]], dtype=np.float64)

    lle = largest_lyapunov_discrete(
        step, jac, np.array([1.0]), n=5_000, n_transient=10
    )
    assert lle == pytest.approx(np.log(c), abs=1e-6)
    assert lle < 0.0


def test_conradi_art_params_orbit_collapses() -> None:
    """ConradiMap at the *art* params (5.46, 4.55): a single orbit collapses.

    The signature density art comes from the transient flow of a dense lattice
    of seeds, not from a chaotic attractor -- so the asymptotic single-orbit LLE
    is non-positive (here ~ -0.02, IC-independent). This is the "quiet" branch.
    """
    m = ConradiMap()
    lle = largest_lyapunov_discrete(
        lambda y: m.step(y),
        lambda y: m.jacobian(y),
        np.array([0.1, 0.1]),
        n=40_000,
        n_transient=3_000,
    )
    assert lle < 0.0


def test_conradi_chaotic_regime_is_positive() -> None:
    """ConradiMap at a genuinely chaotic regime (3.9, 4.6): lambda_1 > 0."""
    m = ConradiMap()
    lle = largest_lyapunov_discrete(
        lambda y: m.step(y, a=3.9, b=4.6),
        lambda y: m.jacobian(y, a=3.9, b=4.6),
        np.array([0.1, 0.1]),
        n=40_000,
        n_transient=3_000,
    )
    assert lle > 0.1


def test_result_is_finite_and_direction_independent() -> None:
    """Different start directions converge to the same leading exponent."""
    a, b = 1.4, 0.3

    def step(y: np.ndarray) -> np.ndarray:
        return np.array([1.0 - a * y[0] ** 2 + y[1], b * y[0]], dtype=np.float64)

    def jac(y: np.ndarray) -> np.ndarray:
        return np.array([[-2.0 * a * y[0], 1.0], [b, 0.0]], dtype=np.float64)

    lle1 = largest_lyapunov_discrete(
        step, jac, np.array([0.1, 0.1]), n=30_000, rng=np.random.default_rng(1)
    )
    lle2 = largest_lyapunov_discrete(
        step, jac, np.array([0.1, 0.1]), n=30_000, rng=np.random.default_rng(99)
    )
    assert np.isfinite(lle1)
    assert lle1 == pytest.approx(lle2, abs=0.01)


def test_invalid_n_raises() -> None:
    with pytest.raises(ValueError, match="n must be"):
        largest_lyapunov_discrete(
            lambda y: y, lambda y: np.eye(1), np.array([0.5]), n=0
        )


# --- largest_lyapunov_discrete_system convenience (CSC-010) ----------------
# "Discrete-map LLE for free" on any registered map: analytic Jacobian when the
# map ships one, else central finite-difference. The proposal's GUI target (a
# Lyapunov panel with a map dropdown) does not exist -- the Lyapunov card only
# sees ODE systems -- so this ships the capability + observable at the core.


def test_discrete_system_henon_fd_jacobian() -> None:
    """HenonMap (no analytic Jacobian) -> FD path -> lambda_1 ~ 0.419."""
    lle = largest_lyapunov_discrete_system(
        HenonMap(), n=40_000, n_transient=2_000
    )
    assert lle == pytest.approx(0.419, abs=0.02)


def test_discrete_system_logistic_r4_is_ln2() -> None:
    """Logistic at r=4 via the convenience (FD Jacobian) -> ln 2."""
    lle = largest_lyapunov_discrete_system(
        Logistic(),
        params={"r": 4.0},
        x0=np.array([0.123]),
        n=60_000,
        n_transient=2_000,
    )
    assert lle == pytest.approx(np.log(2.0), abs=0.02)


def test_discrete_system_conradi_uses_analytic_jacobian() -> None:
    """ConradiMap ships an analytic Jacobian; convenience matches the manual call."""
    m = ConradiMap()
    via_system = largest_lyapunov_discrete_system(
        m, params={"a": 3.9, "b": 4.6}, n=30_000, n_transient=2_000
    )
    manual = largest_lyapunov_discrete(
        lambda y: m.step(y, a=3.9, b=4.6),
        lambda y: m.jacobian(y, a=3.9, b=4.6),
        np.array([0.1, 0.1]),
        n=30_000,
        n_transient=2_000,
    )
    assert via_system > 0.1
    assert via_system == pytest.approx(manual, abs=1e-9)


def test_discrete_system_defaults_to_map_params_and_state() -> None:
    """With no overrides the convenience uses the map's defaults (Henon chaotic)."""
    lle = largest_lyapunov_discrete_system(HenonMap(), n=20_000)
    assert np.isfinite(lle)
    assert lle > 0.0
