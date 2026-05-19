"""Tests for the optional ``numbalsoda`` integrator backend (I2).

The test module splits cleanly in two:

1. **Always-on tests** — verify that the module imports without
   numbalsoda installed, that the integrator is registered, that
   :func:`has_numbalsoda_backend` reports the correct boolean, and
   that calling :meth:`NumbaLSODA.integrate` without the
   ``[performance]`` extra raises a clear :class:`ImportError`.

2. **Gated tests** — guarded by ``importorskip`` on both
   ``numba`` and ``numbalsoda``. They pin the numerical observable:
   integrating Lorenz from a burned-in IC through NumbaLSODA and
   scipy DOP853 agrees on the final state to ~1e-3 in L2 norm
   (chaos amplifies any per-step discrepancy fast; 1e-3 is the
   practical floor that shadowing alone permits at our tolerances).
"""

from __future__ import annotations

from importlib import util as importlib_util

import numpy as np
import pytest

_HAS_NUMBA = importlib_util.find_spec("numba") is not None
_HAS_NUMBALSODA = importlib_util.find_spec("numbalsoda") is not None
_HAS_BACKEND = _HAS_NUMBA and _HAS_NUMBALSODA


# ---------------------------------------------------------------------------
# Always-on tests — exercise the no-extras code paths.
# ---------------------------------------------------------------------------


def test_module_imports_without_optional_extra() -> None:
    """Importing the backend never imports numba / numbalsoda eagerly."""
    from chaotic_systems.integrators import numbalsoda_backend  # noqa: F401


def test_has_numbalsoda_backend_matches_install_state() -> None:
    from chaotic_systems.integrators.numbalsoda_backend import (
        has_numbalsoda_backend,
    )

    assert has_numbalsoda_backend() is _HAS_BACKEND


def test_numbalsoda_registered_in_integrator_registry() -> None:
    """``"NumbaLSODA"`` shows up in the integrator picker regardless of
    whether the optional extra is installed (the GUI lists it
    uniformly; the ImportError only fires on first Run)."""
    from chaotic_systems.integrators import get_integrator, list_integrators

    assert "NumbaLSODA" in list_integrators()
    assert get_integrator("NumbaLSODA").name == "NumbaLSODA"


def test_resolve_funcptr_rejects_plain_python_callable() -> None:
    """A plain Python ``rhs(t, y)`` cannot cross the Fortran boundary."""
    from chaotic_systems.integrators.numbalsoda_backend import _resolve_funcptr

    def rhs(t: float, y: np.ndarray) -> np.ndarray:  # pragma: no cover
        return y

    with pytest.raises(TypeError, match="numba.cfunc"):
        _resolve_funcptr(rhs)


def test_resolve_funcptr_accepts_raw_int_address() -> None:
    """The integer-address escape hatch round-trips unchanged."""
    from chaotic_systems.integrators.numbalsoda_backend import _resolve_funcptr

    assert _resolve_funcptr(12345) == 12345


@pytest.mark.skipif(_HAS_BACKEND, reason="extra is installed; ImportError path unreachable")
def test_integrate_without_extra_raises_clear_importerror() -> None:
    """Without the ``[performance]`` extra, calling integrate raises
    :class:`ImportError` with the canonical install hint."""
    from chaotic_systems.integrators import NumbaLSODA

    with pytest.raises(ImportError, match=r"pip install -e '\.\[performance\]'"):
        NumbaLSODA.integrate(
            42,  # pre-resolved int address; never actually consumed
            (0.0, 1.0),
            np.array([1.0, 1.0, 1.0]),
            n_points=10,
        )


def test_build_t_eval_validates_inputs() -> None:
    from chaotic_systems.integrators.numbalsoda_backend import _build_t_eval

    with pytest.raises(ValueError, match="t_span must be increasing"):
        _build_t_eval(1.0, 0.0, dt=None, n_points=None)
    with pytest.raises(ValueError, match="n_points must be >= 2"):
        _build_t_eval(0.0, 1.0, dt=None, n_points=1)
    with pytest.raises(ValueError, match="dt must be positive"):
        _build_t_eval(0.0, 1.0, dt=-0.1, n_points=None)


def test_build_t_eval_default_grid_has_200_points() -> None:
    from chaotic_systems.integrators.numbalsoda_backend import _build_t_eval

    grid = _build_t_eval(0.0, 1.0, dt=None, n_points=None)
    assert grid.shape == (200,)
    assert grid[0] == 0.0
    assert grid[-1] == pytest.approx(1.0)


def test_build_t_eval_dt_path_endpoints_snap() -> None:
    from chaotic_systems.integrators.numbalsoda_backend import _build_t_eval

    grid = _build_t_eval(0.0, 1.0, dt=0.1, n_points=None)
    assert grid[0] == 0.0
    assert grid[-1] == pytest.approx(1.0)
    assert grid.shape == (11,)


def test_build_t_eval_n_points_wins_over_dt() -> None:
    from chaotic_systems.integrators.numbalsoda_backend import _build_t_eval

    grid = _build_t_eval(0.0, 1.0, dt=0.001, n_points=5)
    assert grid.shape == (5,)


# ---------------------------------------------------------------------------
# Gated tests — require the [performance] extra.
# ---------------------------------------------------------------------------


pytestmark_gated = pytest.mark.skipif(
    not _HAS_BACKEND, reason="numba + numbalsoda not installed"
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
def test_lorenz_numbalsoda_rhs_constructs() -> None:
    """The reference cfunc factory returns an object with ``.address``."""
    from chaotic_systems.integrators.numbalsoda_backend import (
        lorenz_numbalsoda_rhs,
    )

    rhs = lorenz_numbalsoda_rhs()
    assert hasattr(rhs, "address")
    assert isinstance(rhs.address, int)


@pytestmark_gated
def test_numbalsoda_integrate_returns_protocol_compatible_trajectory() -> None:
    """Output is a Trajectory with the right shape and integrator label."""
    from chaotic_systems.core.base import Trajectory
    from chaotic_systems.integrators import NumbaLSODA
    from chaotic_systems.integrators.numbalsoda_backend import (
        lorenz_numbalsoda_rhs,
    )

    rhs = lorenz_numbalsoda_rhs()
    data = np.array([10.0, 28.0, 8.0 / 3.0])
    traj = NumbaLSODA.integrate(
        rhs,
        (0.0, 1.0),
        np.array([1.0, 1.0, 1.0]),
        n_points=50,
        data=data,
    )
    assert isinstance(traj, Trajectory)
    assert traj.t.shape == (50,)
    assert traj.y.shape == (50, 3)
    assert traj.integrator == "NumbaLSODA"
    assert np.isfinite(traj.y).all()


@pytestmark_gated
def test_numbalsoda_matches_scipy_dop853_on_lorenz_short_run() -> None:
    """L2 endpoint error vs scipy DOP853 must be tight on a 5 t.u. run.

    Same numerical observable as the I1 backend parity test — chaos
    amplifies per-step discrepancies fast, so 1e-3 at t=5 is the
    floor that shadowing alone permits at our tolerances.
    """
    from chaotic_systems.integrators import NumbaLSODA
    from chaotic_systems.integrators.numbalsoda_backend import (
        lorenz_numbalsoda_rhs,
    )

    y0 = np.array([1.0, 1.0, 1.0])
    n, t_end = 200, 5.0
    rhs = lorenz_numbalsoda_rhs()
    data = np.array([10.0, 28.0, 8.0 / 3.0])
    traj = NumbaLSODA.integrate(
        rhs,
        (0.0, t_end),
        y0,
        n_points=n,
        rtol=1e-10,
        atol=1e-12,
        data=data,
    )
    scipy_endpoint = _lorenz_scipy(y0, t_end, n)[-1]

    err = float(np.linalg.norm(traj.y[-1] - scipy_endpoint))
    assert err < 1e-3, (
        f"NumbaLSODA vs scipy DOP853 endpoint differ by {err:.6f} "
        f"(tolerance 1e-3); the two backends should agree on the "
        f"same continuous Lorenz orbit to integrator precision."
    )


@pytestmark_gated
def test_numbalsoda_integrate_rejects_unknown_kwargs() -> None:
    """Unsupported kwargs surface clearly instead of being silently dropped."""
    from chaotic_systems.integrators import NumbaLSODA
    from chaotic_systems.integrators.numbalsoda_backend import (
        lorenz_numbalsoda_rhs,
    )

    with pytest.raises(TypeError, match="unexpected kwargs"):
        NumbaLSODA.integrate(
            lorenz_numbalsoda_rhs(),
            (0.0, 1.0),
            np.array([1.0, 1.0, 1.0]),
            n_points=10,
            data=np.array([10.0, 28.0, 8.0 / 3.0]),
            bogus=42,
        )


@pytestmark_gated
def test_numbalsoda_rejects_plain_python_rhs() -> None:
    """A plain Python rhs at integrate() time fails with TypeError."""
    from chaotic_systems.integrators import NumbaLSODA

    def py_rhs(t: float, y: np.ndarray) -> np.ndarray:  # pragma: no cover
        return y

    with pytest.raises(TypeError, match="numba.cfunc"):
        NumbaLSODA.integrate(
            py_rhs,
            (0.0, 1.0),
            np.array([1.0, 1.0, 1.0]),
            n_points=10,
            data=np.array([10.0, 28.0, 8.0 / 3.0]),
        )
