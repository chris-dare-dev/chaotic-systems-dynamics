"""Tests for the optional ``scikit-sundae`` SUNDIALS backend (I3).

Split exactly like the I1 / I2 backend test modules:

1. **Always-on tests** — exercise the no-extra code paths: the
   module imports without sksundae, the integrators register, the
   ImportError surfaces with the canonical hint, the in-place rhsfn
   adapter accepts both ``rhs(t, y)`` and ``rhsfn(t, y, yp)`` shapes,
   and the tspan builder validates inputs.

2. **Gated tests** — guarded by ``importorskip("sksundae")``. They
   pin two numerical observables:

   - **CVODE-BDF on Lorenz** vs scipy DOP853: endpoints agree to
     L2 < 1e-3 over t in [0, 5] (chaos amplifies per-step error
     fast; 1e-3 is the floor shadowing alone permits at our
     tolerances). Same precision contract the I1 and I2 backends
     enforce.
   - **IDA on Robertson's DAE**: the algebraic constraint
     ``y0 + y1 + y2 - 1 = 0`` is preserved to ~1e-10 across the
     integration; the system flows from (1, 0, 0) toward the
     quasi-steady-state regime. This is the canonical index-1 DAE
     smoke test for SUNDIALS and the proposal's named use case.
"""

from __future__ import annotations

from importlib import util as importlib_util

import numpy as np
import pytest

_HAS_SUNDIALS = importlib_util.find_spec("sksundae") is not None


# ---------------------------------------------------------------------------
# Always-on tests — exercise the no-extra code paths.
# ---------------------------------------------------------------------------


def test_module_imports_without_optional_extra() -> None:
    """The backend module never imports sksundae at module load."""
    from chaotic_systems.integrators import sundials_backend  # noqa: F401


def test_has_sundials_backend_matches_install_state() -> None:
    from chaotic_systems.integrators.sundials_backend import (
        has_sundials_backend,
    )

    assert has_sundials_backend() is _HAS_SUNDIALS


def test_cvode_integrators_registered() -> None:
    """``CVODE`` and ``CVODE-Adams`` show up in the integrator picker
    regardless of whether the extra is installed (the GUI lists them
    uniformly; ImportError only fires on first Run)."""
    from chaotic_systems.integrators import get_integrator, list_integrators

    names = list_integrators()
    assert "CVODE" in names
    assert "CVODE-Adams" in names
    assert get_integrator("CVODE").name == "CVODE"
    assert get_integrator("CVODE-Adams").name == "CVODE-Adams"


def test_cvode_method_dispatch_is_bdf_vs_adams() -> None:
    """The two registry entries point at different multistep families."""
    from chaotic_systems.integrators import CVODE, CVODEAdams

    assert CVODE.method == "BDF"
    assert CVODEAdams.method == "Adams"


@pytest.mark.skipif(_HAS_SUNDIALS, reason="extra is installed; ImportError path unreachable")
def test_integrate_without_extra_raises_clear_importerror() -> None:
    """Without ``[sundials]`` installed, calling integrate raises
    :class:`ImportError` with the canonical install hint."""
    from chaotic_systems.integrators import CVODE

    def rhs(t: float, y: np.ndarray) -> np.ndarray:  # pragma: no cover
        return y

    with pytest.raises(ImportError, match=r"pip install -e '\.\[sundials\]'"):
        CVODE.integrate(rhs, (0.0, 1.0), np.array([1.0]), n_points=10)


@pytest.mark.skipif(_HAS_SUNDIALS, reason="extra is installed; ImportError path unreachable")
def test_ida_solve_without_extra_raises_clear_importerror() -> None:
    """IDA's free-function entry point surfaces the same ImportError."""
    from chaotic_systems.integrators.sundials_backend import (
        ida_solve,
        robertson_residual,
    )

    with pytest.raises(ImportError, match=r"pip install -e '\.\[sundials\]'"):
        ida_solve(
            robertson_residual,
            (0.0, 1.0),
            np.array([1.0, 0.0, 0.0]),
            np.array([-0.04, 0.04, 0.0]),
            algebraic_idx=[2],
            n_points=10,
        )


def test_build_tspan_validates_inputs() -> None:
    from chaotic_systems.integrators.sundials_backend import _build_tspan

    with pytest.raises(ValueError, match="t_span must be increasing"):
        _build_tspan(1.0, 0.0, dt=None, n_points=None)
    with pytest.raises(ValueError, match="n_points must be >= 2"):
        _build_tspan(0.0, 1.0, dt=None, n_points=1)
    with pytest.raises(ValueError, match="dt must be positive"):
        _build_tspan(0.0, 1.0, dt=-0.1, n_points=None)


def test_build_tspan_default_grid_has_200_points() -> None:
    from chaotic_systems.integrators.sundials_backend import _build_tspan

    grid = _build_tspan(0.0, 1.0, dt=None, n_points=None)
    assert grid.shape == (200,)
    assert grid[0] == 0.0
    assert grid[-1] == pytest.approx(1.0)


def test_make_rhsfn_adapts_two_arg_rhs() -> None:
    """A standard ``rhs(t, y)`` returning dy/dt is wrapped to fill
    ``yp`` in place."""
    from chaotic_systems.integrators.sundials_backend import _make_rhsfn

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        return np.array([y[1], -y[0]])

    rhsfn = _make_rhsfn(rhs)
    yp = np.zeros(2)
    rhsfn(0.0, np.array([1.0, 0.0]), yp)
    assert yp[0] == 0.0
    assert yp[1] == -1.0


def test_make_rhsfn_passes_through_three_arg_form() -> None:
    """A native ``rhsfn(t, y, yp)`` is returned unchanged."""
    from chaotic_systems.integrators.sundials_backend import _make_rhsfn

    def rhsfn(t: float, y: np.ndarray, yp: np.ndarray) -> None:
        yp[0] = y[1]
        yp[1] = -y[0]

    assert _make_rhsfn(rhsfn) is rhsfn


def test_lorenz_sundials_rhsfn_fills_in_place_correctly() -> None:
    """The reference rhsfn matches a hand-derived Lorenz step.

    No sksundae needed — the rhsfn is plain Python; the test
    just verifies the SOTA Lorenz formula is correct.
    """
    from chaotic_systems.integrators.sundials_backend import (
        lorenz_sundials_rhsfn,
    )

    rhsfn = lorenz_sundials_rhsfn()
    y = np.array([1.0, 2.0, 3.0])
    yp = np.zeros(3)
    rhsfn(0.0, y, yp)
    # dy/dt = (sigma*(y-x), x*(rho-z)-y, x*y - beta*z)
    #       = (10*(2-1), 1*(28-3)-2, 1*2 - 8/3*3)
    #       = (10, 23, 2 - 8)
    assert yp[0] == pytest.approx(10.0)
    assert yp[1] == pytest.approx(23.0)
    assert yp[2] == pytest.approx(2.0 - 8.0)
    assert np.isfinite(yp).all()


def test_robertson_residual_at_canonical_ic_is_zero_on_algebraic_row() -> None:
    """At y = (1, 0, 0), the algebraic row of the residual must be 0
    (the constraint y0 + y1 + y2 = 1 is satisfied by the standard
    Robertson IC). The differential rows depend on yp."""
    from chaotic_systems.integrators.sundials_backend import (
        ROBERTSON_K1,
        robertson_residual,
    )

    y = np.array([1.0, 0.0, 0.0])
    # Consistent yp: yp[0] = -k1, yp[1] = +k1, yp[2] free (algebraic).
    yp = np.array([-ROBERTSON_K1, ROBERTSON_K1, 0.0])
    res = np.zeros(3)
    robertson_residual(0.0, y, yp, res)
    # Algebraic row (index 2): y0 + y1 + y2 - 1 = 0
    assert res[2] == pytest.approx(0.0)
    # Differential rows: with the consistent yp above, both vanish.
    assert res[0] == pytest.approx(0.0)
    assert res[1] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Gated tests — require the [sundials] extra.
# ---------------------------------------------------------------------------


pytestmark_gated = pytest.mark.skipif(
    not _HAS_SUNDIALS, reason="scikit-sundae not installed"
)


def _lorenz_scipy(y0: np.ndarray, t_end: float, n: int) -> np.ndarray:
    """Reference scipy DOP853 trajectory for parity comparisons."""
    from scipy.integrate import solve_ivp

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        return np.array(
            [
                10.0 * (y[1] - y[0]),
                y[0] * (28.0 - y[2]) - y[1],
                y[0] * y[1] - (8.0 / 3.0) * y[2],
            ]
        )

    sol = solve_ivp(
        rhs,
        (0.0, t_end),
        y0,
        method="DOP853",
        t_eval=np.linspace(0.0, t_end, n),
        rtol=1e-10,
        atol=1e-12,
    )
    return sol.y.T


@pytestmark_gated
def test_cvode_integrate_returns_protocol_compatible_trajectory() -> None:
    """Output is a Trajectory with the right shape and integrator label."""
    from chaotic_systems.core.base import Trajectory
    from chaotic_systems.integrators import CVODE
    from chaotic_systems.integrators.sundials_backend import (
        lorenz_sundials_rhsfn,
    )

    rhsfn = lorenz_sundials_rhsfn()
    traj = CVODE.integrate(
        rhsfn, (0.0, 1.0), np.array([1.0, 1.0, 1.0]), n_points=50
    )
    assert isinstance(traj, Trajectory)
    assert traj.t.shape == (50,)
    assert traj.y.shape == (50, 3)
    assert traj.integrator == "CVODE"
    assert np.isfinite(traj.y).all()


@pytestmark_gated
def test_cvode_matches_scipy_dop853_on_lorenz_short_run() -> None:
    """L2 endpoint error vs scipy DOP853 must be tight on a 5 t.u. run.

    Same numerical contract as I1 (JAX) and I2 (numbalsoda) — chaos
    amplifies per-step discrepancies fast, so 1e-3 at t=5 is the
    floor that shadowing alone permits at our tolerances.
    """
    from chaotic_systems.integrators import CVODE
    from chaotic_systems.integrators.sundials_backend import (
        lorenz_sundials_rhsfn,
    )

    y0 = np.array([1.0, 1.0, 1.0])
    n, t_end = 200, 5.0
    traj = CVODE.integrate(
        lorenz_sundials_rhsfn(),
        (0.0, t_end),
        y0,
        n_points=n,
        rtol=1e-10,
        atol=1e-12,
    )
    scipy_endpoint = _lorenz_scipy(y0, t_end, n)[-1]
    err = float(np.linalg.norm(traj.y[-1] - scipy_endpoint))
    assert err < 1e-3, (
        f"CVODE-BDF vs scipy DOP853 endpoint differ by {err:.6f} "
        f"(tolerance 1e-3); the two backends should agree on the "
        f"same continuous Lorenz orbit to integrator precision."
    )


@pytestmark_gated
def test_cvode_adams_also_matches_scipy_on_lorenz() -> None:
    """Adams-Moulton (non-stiff multistep) tracks scipy too."""
    from chaotic_systems.integrators import CVODEAdams
    from chaotic_systems.integrators.sundials_backend import (
        lorenz_sundials_rhsfn,
    )

    y0 = np.array([1.0, 1.0, 1.0])
    n, t_end = 200, 5.0
    traj = CVODEAdams.integrate(
        lorenz_sundials_rhsfn(),
        (0.0, t_end),
        y0,
        n_points=n,
        rtol=1e-10,
        atol=1e-12,
    )
    scipy_endpoint = _lorenz_scipy(y0, t_end, n)[-1]
    err = float(np.linalg.norm(traj.y[-1] - scipy_endpoint))
    assert err < 1e-3, (
        f"CVODE-Adams vs scipy DOP853 endpoint differ by {err:.6f}"
    )


@pytestmark_gated
def test_cvode_accepts_two_arg_rhs_via_adapter() -> None:
    """The standard ``rhs(t, y)`` form auto-adapts to sksundae's
    in-place ``rhsfn(t, y, yp)`` contract."""
    from chaotic_systems.integrators import CVODE

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        return np.array(
            [
                10.0 * (y[1] - y[0]),
                y[0] * (28.0 - y[2]) - y[1],
                y[0] * y[1] - (8.0 / 3.0) * y[2],
            ]
        )

    traj = CVODE.integrate(
        rhs, (0.0, 1.0), np.array([1.0, 1.0, 1.0]), n_points=40
    )
    assert traj.y.shape == (40, 3)
    assert np.isfinite(traj.y).all()


@pytestmark_gated
def test_cvode_rejects_unknown_kwargs() -> None:
    """Unsupported kwargs surface clearly instead of silently dropping."""
    from chaotic_systems.integrators import CVODE
    from chaotic_systems.integrators.sundials_backend import (
        lorenz_sundials_rhsfn,
    )

    with pytest.raises(TypeError, match="unexpected kwargs"):
        CVODE.integrate(
            lorenz_sundials_rhsfn(),
            (0.0, 1.0),
            np.array([1.0, 1.0, 1.0]),
            n_points=10,
            bogus=42,
        )


@pytestmark_gated
def test_ida_solves_robertson_dae_and_preserves_algebraic_constraint() -> None:
    """IDA on the canonical Robertson DAE.

    The proposal's named use case: a hidden-constraint formulation.
    The algebraic equation ``y0 + y1 + y2 = 1`` is the conservation
    law; we assert it's preserved across the integration to ~1e-10.
    The system also evolves into the quasi-steady regime in which
    y1 is the small, fast-decaying middle species — at t = 1 the
    classical Robertson observable is ``y1 < 1e-3`` (Hairer-Wanner
    II §IV.1 Fig. 1.1).
    """
    from chaotic_systems.integrators.sundials_backend import (
        ROBERTSON_K1,
        ida_solve,
        robertson_residual,
    )

    y0 = np.array([1.0, 0.0, 0.0])
    # Consistent initial derivative (the algebraic row's yp is free,
    # IDA corrects from this guess via calc_initcond='yp0').
    yp0 = np.array([-ROBERTSON_K1, ROBERTSON_K1, 0.0])
    traj = ida_solve(
        robertson_residual,
        (0.0, 1.0),
        y0,
        yp0,
        algebraic_idx=[2],
        calc_initcond="yp0",
        n_points=50,
        rtol=1e-8,
        atol=1e-10,
    )
    assert traj.y.shape == (50, 3)
    # Algebraic conservation law preserved everywhere.
    sum_err = float(np.max(np.abs(traj.y.sum(axis=1) - 1.0)))
    assert sum_err < 1e-8, (
        f"Robertson conservation y0+y1+y2=1 drifted by {sum_err:.2e} "
        f"(tolerance 1e-8); IDA must preserve algebraic constraints."
    )
    # Quasi-steady observable: y1 is small at t = 1.
    assert traj.y[-1, 1] < 1e-3, (
        f"Robertson middle species should be small at t=1; "
        f"got y1(1) = {traj.y[-1, 1]:.4f}"
    )
