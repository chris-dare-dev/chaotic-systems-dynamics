"""Lyapunov exponent estimation.

Two methods are exposed:

- :func:`largest_lyapunov_two_trajectory` — Benettin's two-trajectory
  method. Integrate the system and a nearby copy; periodically rescale
  the separation to keep it small; track the average log-stretch. The
  result converges to the largest Lyapunov exponent
  :math:`\\lambda_1`. This is the simplest reliable estimator and is the
  one used by the example in ``examples/lyapunov_lorenz.py``.
- :func:`lyapunov_spectrum` — full spectrum via the variational
  (tangent-space) equations and continuous QR reorthonormalization, also
  known as Benettin's algorithm. Requires the system's Jacobian
  :math:`\\partial f / \\partial y`; if not supplied analytically we
  compute it by finite differences.

Both routines call :meth:`DynamicalSystem.rhs` (the public hook), so
subclasses that override ``rhs`` for non-autonomous time gating or
similar concerns are respected.

References
----------
- G. Benettin, L. Galgani, A. Giorgilli, J.-M. Strelcyn, *Lyapunov
  Characteristic Exponents for smooth dynamical systems and for
  Hamiltonian systems; a method for computing all of them.* Meccanica
  15 (1980), 9-30.
- S. H. Strogatz, *Nonlinear Dynamics and Chaos*, 2nd ed., Westview
  Press, 2015 — see chapter 10.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

import numpy as np
from scipy.integrate import solve_ivp

from chaotic_systems.core.base import DynamicalSystem, FloatArray


def _public_rhs(
    system: DynamicalSystem, params: Mapping[str, float]
) -> Callable[[float, FloatArray], FloatArray]:
    """Wrap the system's *public* ``rhs(t, y, **params)`` for ``solve_ivp``."""

    def fun(t: float, y: FloatArray) -> FloatArray:
        return system.rhs(t, y, **params)

    return fun


def largest_lyapunov_two_trajectory(
    system: DynamicalSystem,
    y0: FloatArray | None = None,
    params: Mapping[str, float] | None = None,
    t_transient: float = 50.0,
    t_total: float = 500.0,
    dt: float = 1.0,
    delta0: float = 1e-8,
    rtol: float = 1e-9,
    atol: float = 1e-12,
    rng: np.random.Generator | None = None,
) -> float:
    """Estimate the largest Lyapunov exponent via two trajectories.

    Algorithm
    ---------
    1. Integrate from ``y0`` for ``t_transient`` to land on the attractor.
    2. Make a perturbed copy at distance ``delta0`` in a random direction.
    3. Repeatedly integrate **both trajectories jointly** as one 2*state_dim
       system over ``dt``, measure the new separation
       :math:`\\delta_k`, accumulate :math:`\\log(\\delta_k / \\delta_0)`,
       then renormalize the perturbed trajectory back to distance
       :math:`\\delta_0`.
    4. After ``N = (t_total - t_transient) / dt`` steps, the largest
       Lyapunov exponent is the average log-stretch rate.

    Parameters
    ----------
    t_transient
        Time discarded as transient.
    t_total
        Total integration time (including transient).
    dt
        Re-orthonormalization interval. Too small wastes work; too large
        lets the perturbation align with stretching and saturate.
        :math:`O(1)` is typical for Lorenz.
    delta0
        Initial perturbation magnitude. Should be small (well inside the
        linear regime) but not so small as to hit floating-point noise.
    rng
        ``numpy.random.Generator`` for the perturbation direction.

    Notes
    -----
    The joint-integration trick (one ``solve_ivp`` call per step instead
    of two) halves the per-step Python-level overhead and improves end-
    to-end runtime by ~2x on cheap RHS evaluations.
    """
    if rng is None:
        rng = np.random.default_rng(0xC0FFEE)
    y_start = (
        system.initial_state if y0 is None else np.asarray(y0, dtype=np.float64)
    )
    merged_params = system.merged_params(params)
    fun = _public_rhs(system, merged_params)
    n = system.state_dim

    # 1. Integrate off the transient.
    sol = solve_ivp(
        fun,
        (0.0, t_transient),
        y_start,
        method="DOP853",
        rtol=rtol,
        atol=atol,
        dense_output=False,
    )
    y_ref = sol.y[:, -1].copy()

    # 2. Build a perturbed copy.
    direction = rng.standard_normal(n)
    direction /= np.linalg.norm(direction)
    y_pert = y_ref + delta0 * direction

    # 3. Iterate. The joint state is z = [y_ref; y_pert] of length 2n.
    def joint_rhs(t: float, z: FloatArray) -> FloatArray:
        out = np.empty_like(z)
        out[:n] = fun(t, z[:n])
        out[n:] = fun(t, z[n:])
        return out

    n_steps = max(1, int(np.floor((t_total - t_transient) / dt)))
    log_sum = 0.0
    t_now = t_transient
    z = np.concatenate([y_ref, y_pert])
    for _ in range(n_steps):
        t_next = t_now + dt
        sol = solve_ivp(
            joint_rhs,
            (t_now, t_next),
            z,
            method="DOP853",
            rtol=rtol,
            atol=atol,
        )
        z = sol.y[:, -1]
        y_ref = z[:n]
        y_pert = z[n:]
        diff = y_pert - y_ref
        d = float(np.linalg.norm(diff))
        if d == 0.0:  # pragma: no cover - numerically extremely unlikely
            d = delta0
        log_sum += np.log(d / delta0)
        # Renormalize.
        y_pert = y_ref + (delta0 / d) * diff
        z = np.concatenate([y_ref, y_pert])
        t_now = t_next

    return float(log_sum / (n_steps * dt))


def _finite_diff_jacobian(
    fun: Callable[[float, FloatArray], FloatArray],
    t: float,
    y: FloatArray,
    eps: float = 1e-7,
) -> FloatArray:
    """Central-difference Jacobian. ``O(n)`` extra RHS evaluations."""
    n = y.shape[0]
    J = np.empty((n, n), dtype=np.float64)
    for i in range(n):
        e = np.zeros(n)
        e[i] = eps
        J[:, i] = (fun(t, y + e) - fun(t, y - e)) / (2.0 * eps)
    return J


def lyapunov_spectrum(
    system: DynamicalSystem,
    y0: FloatArray | None = None,
    params: Mapping[str, float] | None = None,
    n_exponents: int | None = None,
    t_transient: float = 50.0,
    t_total: float = 500.0,
    dt: float = 1.0,
    rtol: float = 1e-9,
    atol: float = 1e-12,
    jacobian: Callable[[float, FloatArray, Mapping[str, float]], FloatArray] | None = None,
    rng: np.random.Generator | None = None,
) -> FloatArray:
    """Full Lyapunov spectrum via continuous QR reorthonormalization.

    The variational equations are

    .. math::

        \\dot \\Phi = J(t, y) \\, \\Phi,

    where :math:`J = \\partial f / \\partial y`. We integrate ``y`` and a
    matrix :math:`\\Phi` of perturbation vectors jointly. Every ``dt``,
    we QR-decompose :math:`\\Phi = QR`, accumulate
    :math:`\\sum \\log |R_{ii}|`, reset :math:`\\Phi \\leftarrow Q`.

    Returns the array of exponents :math:`\\lambda_1 \\geq \\lambda_2
    \\geq \\dots`. ``n_exponents`` defaults to the full state dimension.
    """
    if rng is None:
        rng = np.random.default_rng(0xBADC0DE)
    n = system.state_dim
    k = n if n_exponents is None else int(n_exponents)
    if not 1 <= k <= n:
        raise ValueError(f"n_exponents must be in [1, {n}], got {k}")

    y_start = (
        system.initial_state if y0 is None else np.asarray(y0, dtype=np.float64)
    )
    merged_params = system.merged_params(params)
    fun = _public_rhs(system, merged_params)

    if jacobian is None:

        def jac(t: float, y: FloatArray) -> FloatArray:
            return _finite_diff_jacobian(fun, t, y)
    else:

        def jac(t: float, y: FloatArray) -> FloatArray:
            return jacobian(t, y, merged_params)

    # Burn off transient.
    sol = solve_ivp(
        fun, (0.0, t_transient), y_start, method="DOP853", rtol=rtol, atol=atol
    )
    y = sol.y[:, -1].copy()

    # Initialise tangent matrix Phi as a random orthonormal n x k matrix.
    Phi, _ = np.linalg.qr(rng.standard_normal((n, k)))

    # Joint flow on (y, Phi) flattened.
    def joint_rhs(t: float, z: FloatArray) -> FloatArray:
        y_local = z[:n]
        Phi_local = z[n:].reshape(n, k)
        f_y = fun(t, y_local)
        J = jac(t, y_local)
        dPhi = J @ Phi_local
        out = np.empty_like(z)
        out[:n] = f_y
        out[n:] = dPhi.ravel()
        return out

    n_steps = max(1, int(np.floor((t_total - t_transient) / dt)))
    log_sum = np.zeros(k, dtype=np.float64)
    t_now = t_transient
    z = np.concatenate([y, Phi.ravel()])
    for _ in range(n_steps):
        t_next = t_now + dt
        sol = solve_ivp(
            joint_rhs, (t_now, t_next), z, method="DOP853", rtol=rtol, atol=atol
        )
        z = sol.y[:, -1]
        y = z[:n]
        Phi = z[n:].reshape(n, k)
        Q, R = np.linalg.qr(Phi)
        # Lyapunov contribution is log|R_ii|.
        diag = np.abs(np.diag(R))
        diag = np.where(diag == 0.0, 1e-300, diag)
        log_sum += np.log(diag)
        Phi = Q
        z = np.concatenate([y, Phi.ravel()])
        t_now = t_next

    return log_sum / (n_steps * dt)


__all__ = [
    "largest_lyapunov_two_trajectory",
    "lyapunov_spectrum",
]
