"""Tests for the optional JAX / diffrax integrator backend (I1).

These tests are gated by an ``importorskip`` on ``jax`` / ``diffrax``:
contributors without the ``[jax]`` extra installed see them skipped
rather than failing.

The reference observables:

1. **Parity with scipy** — integrating Lorenz from (1, 1, 1) over
   t in [0, 5] with ``JAX-Tsit5`` (or ``JAX-RK45``) and the scipy
   ``DOP853`` integrator must agree on the final state to within
   1e-3 in L2 norm. This pins both backends to the same continuous-
   time orbit (chaos amplifies any per-step discrepancy fast, so
   1e-3 is the practical floor we can hold without diverging from
   shadowing alone).

2. **Lyapunov divergence under vmap** — batch 4 Lorenz orbits
   starting at attractor-burned-in IC + perturbations
   {0, 1e-3, 1e-2, 1e-1} on the x-axis. After t = 10 the spread
   between the 0 and 1e-1 trajectories must exceed 1.0 (the
   attractor's natural diameter scale). This is the observable that
   makes basin-of-attraction maps tractable — the batch ran in one
   vmapped XLA kernel.

3. **Shape / arity** — the integrator's Trajectory output matches
   the protocol contract, ``vmap_trajectories`` returns
   ``(N,)``-and-``(B, N, state_dim)`` arrays, the 2-arg ``rhs(t, y)``
   form auto-adapts to diffrax's 3-arg ``rhs(t, y, args)`` form.
"""

from __future__ import annotations

import numpy as np
import pytest

# Gate the whole module on the optional extra.
pytest.importorskip("jax")
pytest.importorskip("diffrax")


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


def test_has_jax_backend_reports_true_when_installed() -> None:
    from chaotic_systems.integrators.jax_backend import has_jax_backend

    assert has_jax_backend() is True


def test_jax_integrators_registered() -> None:
    """Both JAX-RK45 and JAX-Tsit5 must show up in the integrator registry."""
    from chaotic_systems.integrators import get_integrator, list_integrators

    names = list_integrators()
    assert "JAX-RK45" in names
    assert "JAX-Tsit5" in names
    assert get_integrator("JAX-Tsit5").name == "JAX-Tsit5"
    assert get_integrator("JAX-RK45").name == "JAX-RK45"


def test_jax_tsit5_integrate_returns_protocol_compatible_trajectory() -> None:
    """The output is a Trajectory with the right shape and integrator label."""
    from chaotic_systems.core.base import Trajectory
    from chaotic_systems.integrators import JaxTsit5
    from chaotic_systems.integrators.jax_backend import lorenz_jax_rhs

    rhs = lorenz_jax_rhs()
    traj = JaxTsit5.integrate(
        rhs, (0.0, 1.0), np.array([1.0, 1.0, 1.0]), n_points=50
    )
    assert isinstance(traj, Trajectory)
    assert traj.t.shape == (50,)
    assert traj.y.shape == (50, 3)
    assert traj.integrator == "JAX-Tsit5"
    assert np.isfinite(traj.y).all()


def test_jax_tsit5_matches_scipy_dop853_on_lorenz_short_run() -> None:
    """L2 endpoint error vs scipy DOP853 must be tight on a 5 t.u. run."""
    from chaotic_systems.integrators import JaxTsit5
    from chaotic_systems.integrators.jax_backend import lorenz_jax_rhs

    y0 = np.array([1.0, 1.0, 1.0])
    n, t_end = 200, 5.0
    rhs = lorenz_jax_rhs()
    jax_traj = JaxTsit5.integrate(
        rhs, (0.0, t_end), y0, n_points=n, rtol=1e-10, atol=1e-12
    )
    scipy_traj = _lorenz_scipy(y0, t_end, n)

    err = float(np.linalg.norm(jax_traj.y[-1] - scipy_traj[-1]))
    assert err < 1e-3, (
        f"JAX-Tsit5 vs scipy DOP853 endpoint differ by {err:.6f} "
        f"(tolerance 1e-3); the two backends should agree on the "
        f"same continuous Lorenz orbit to integrator precision."
    )


def test_jax_rk45_also_matches_scipy() -> None:
    """JAX-RK45 (Dopri5) is the same Butcher tableau as scipy's RK45."""
    from chaotic_systems.integrators import JaxRK45
    from chaotic_systems.integrators.jax_backend import lorenz_jax_rhs

    y0 = np.array([1.0, 1.0, 1.0])
    n, t_end = 200, 5.0
    rhs = lorenz_jax_rhs()
    jax_traj = JaxRK45.integrate(
        rhs, (0.0, t_end), y0, n_points=n, rtol=1e-10, atol=1e-12
    )
    scipy_traj = _lorenz_scipy(y0, t_end, n)
    err = float(np.linalg.norm(jax_traj.y[-1] - scipy_traj[-1]))
    assert err < 1e-3, f"JAX-RK45 vs scipy DOP853 endpoint differ by {err:.6f}"


def test_jax_integrate_rejects_unknown_kwargs() -> None:
    """Unsupported kwargs surface clearly instead of being silently dropped."""
    from chaotic_systems.integrators import JaxTsit5
    from chaotic_systems.integrators.jax_backend import lorenz_jax_rhs

    with pytest.raises(TypeError, match="unexpected kwargs"):
        JaxTsit5.integrate(
            lorenz_jax_rhs(),
            (0.0, 1.0),
            np.array([1.0, 1.0, 1.0]),
            n_points=50,
            bogus=42,
        )


def test_vmap_trajectories_returns_batched_shapes() -> None:
    from chaotic_systems.integrators.jax_backend import (
        lorenz_jax_rhs,
        vmap_trajectories,
    )

    rhs = lorenz_jax_rhs()
    y0_batch = np.array(
        [
            [1.0, 1.0, 1.0],
            [1.001, 1.0, 1.0],
            [1.01, 1.0, 1.0],
            [1.1, 1.0, 1.0],
        ]
    )
    ts, ys = vmap_trajectories(rhs, (0.0, 2.0), y0_batch, n_points=50)
    assert ts.shape == (50,)
    assert ys.shape == (4, 50, 3)
    assert np.isfinite(ys).all()
    # All four trajectories start from the supplied ICs.
    np.testing.assert_allclose(ys[:, 0, :], y0_batch, atol=1e-6)


def test_vmap_trajectories_validates_y0_shape() -> None:
    from chaotic_systems.integrators.jax_backend import (
        lorenz_jax_rhs,
        vmap_trajectories,
    )

    with pytest.raises(ValueError, match="2-D"):
        vmap_trajectories(
            lorenz_jax_rhs(), (0.0, 1.0), np.array([1.0, 1.0, 1.0])
        )
    with pytest.raises(ValueError, match="at least one"):
        vmap_trajectories(
            lorenz_jax_rhs(), (0.0, 1.0), np.zeros((0, 3))
        )
    with pytest.raises(ValueError, match="t_span"):
        vmap_trajectories(
            lorenz_jax_rhs(), (1.0, 0.0), np.array([[1.0, 1.0, 1.0]])
        )


def test_vmap_lorenz_diverges_under_perturbation() -> None:
    """The headline observable — vmap'd Lorenz orbits show Lyapunov divergence.

    Burn in to the attractor first, then batch 4 ICs at offsets
    {0, 1e-3, 1e-2, 1e-1} on the x-axis. After t = 10 on-attractor
    units the asymptotic prediction is

        eps_max * exp(lambda_1 * 10) approx 0.1 * exp(9.05) approx 850

    bounded by the attractor diameter (~30-50). We assert the
    max pairwise endpoint separation > 1.0 and < 100.0 — well into
    the diverged regime, well under any numerical-blowup floor.
    """
    from chaotic_systems.integrators.jax_backend import (
        lorenz_jax_rhs,
        vmap_trajectories,
    )

    # Burn in: scipy is fine here, the burn-in IC is the seed for the
    # vmap'd JAX run.
    burned = _lorenz_scipy(np.array([1.0, 1.0, 1.0]), t_end=50.0, n=2)
    attractor_ic = burned[-1]

    y0_batch = np.stack(
        [attractor_ic + np.array([eps, 0.0, 0.0]) for eps in (0.0, 1e-3, 1e-2, 1e-1)]
    )
    rhs = lorenz_jax_rhs()
    ts, ys = vmap_trajectories(
        rhs, (0.0, 10.0), y0_batch, n_points=200, rtol=1e-8, atol=1e-10
    )
    assert ys.shape == (4, 200, 3)
    endpoints = ys[:, -1, :]
    pair_sep = float(np.linalg.norm(endpoints[0] - endpoints[3]))
    assert pair_sep > 1.0, (
        f"expected unperturbed vs eps=1e-1 separation > 1.0 at t=10; "
        f"got {pair_sep:.4f}"
    )
    # Sanity: trajectories stay bounded on the attractor.
    assert np.abs(ys).max() < 100.0


def test_two_arg_rhs_auto_adapts_to_diffrax_three_arg_form() -> None:
    """A user-supplied rhs(t, y) closure must work without manual wrapping."""
    import jax.numpy as jnp

    from chaotic_systems.integrators import JaxTsit5

    def rhs(t: float, y) -> object:
        return jnp.array(
            [
                10.0 * (y[1] - y[0]),
                y[0] * (28.0 - y[2]) - y[1],
                y[0] * y[1] - (8.0 / 3.0) * y[2],
            ]
        )

    traj = JaxTsit5.integrate(
        rhs, (0.0, 1.0), np.array([1.0, 1.0, 1.0]), n_points=40
    )
    assert traj.y.shape == (40, 3)
    assert np.isfinite(traj.y).all()
