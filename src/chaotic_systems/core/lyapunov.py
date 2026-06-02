"""Lyapunov exponent estimation and derived attractor diagnostics.

Two estimators are exposed:

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

In addition, :func:`kaplan_yorke_dimension` returns the
Kaplan-Yorke (Lyapunov) dimension derived from a pre-computed spectrum
— a scalar fractal-dimension summary of the attractor.

References
----------
- G. Benettin, L. Galgani, A. Giorgilli, J.-M. Strelcyn, *Lyapunov
  Characteristic Exponents for smooth dynamical systems and for
  Hamiltonian systems; a method for computing all of them.* Meccanica
  15 (1980), 9-30.
- J. L. Kaplan, J. A. Yorke, *Chaotic behavior of multidimensional
  difference equations*, in *Functional Differential Equations and
  Approximation of Fixed Points* (H.-O. Peitgen, H.-O. Walther, eds.),
  Lecture Notes in Mathematics 730, Springer (1979), 204-227.
- J. C. Sprott, *Chaos and Time-Series Analysis*, Oxford University
  Press, 2003 — chapter 5 derives D_KY values for Lorenz, Rossler, and
  other canonical attractors.
- S. H. Strogatz, *Nonlinear Dynamics and Chaos*, 2nd ed., Westview
  Press, 2015 — see chapter 10.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

import numpy as np
from scipy.integrate import solve_ivp

from chaotic_systems.core.base import DynamicalSystem, FloatArray

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from chaotic_systems.core.discrete import DiscreteSystem


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


# ---------------------------------------------------------------------------
# Discrete-map largest Lyapunov exponent (tangent-map renormalization).
# ---------------------------------------------------------------------------

# Default direction seed for the initial tangent vector. The largest exponent
# is generically independent of the (non-degenerate) start direction, so the
# seed only fixes reproducibility, not the answer.
_DISCRETE_TANGENT_SEED: int = 0xA11A1


def largest_lyapunov_discrete(
    step_fn: Callable[[FloatArray], FloatArray],
    jacobian_fn: Callable[[FloatArray], FloatArray],
    x0: FloatArray,
    n: int = 20_000,
    n_transient: int = 1_000,
    rng: np.random.Generator | None = None,
) -> float:
    r"""Largest Lyapunov exponent of a discrete map via tangent-map renormalization.

    This is the map analogue of :func:`lyapunov_spectrum`'s leading exponent:
    instead of integrating the variational ODE, it multiplies a single tangent
    vector by the map's Jacobian at each iterate and renormalizes, accumulating
    the average log-stretch (Benettin's algorithm specialized to a map and a
    single tangent direction):

    .. math::

        \lambda_1 = \lim_{N\to\infty} \frac{1}{N}
            \sum_{k=0}^{N-1} \log \lVert J(x_k)\, v_k \rVert,
        \qquad v_{k+1} = \frac{J(x_k)\, v_k}{\lVert J(x_k)\, v_k \rVert}.

    The Jacobian is supplied as a **callable argument** — there is deliberately
    no ``jacobian`` hook on the :class:`~chaotic_systems.core.discrete.DiscreteSystem`
    ABC, so this estimator leaves the base class, its subclasses, and the
    ``solve_ivp``-based ODE estimators above entirely untouched. Use it as::

        from chaotic_systems.systems.conradi import ConradiMap
        m = ConradiMap()
        lle = largest_lyapunov_discrete(
            step_fn=lambda y: m.step(y),
            jacobian_fn=lambda y: m.jacobian(y),
            x0=np.array([0.1, 0.1]),
        )

    Parameters
    ----------
    step_fn
        The map ``x -> f(x)``; returns a ``(d,)`` array.
    jacobian_fn
        The Jacobian ``x -> J(x)``; returns a ``(d, d)`` array (a ``(1, 1)``
        matrix for a 1-D map such as the logistic map).
    x0
        Initial state, shape ``(d,)``.
    n
        Number of accumulation iterations (after the transient).
    n_transient
        Iterations discarded so the orbit settles onto the attractor before
        accumulation begins.
    rng
        Generator for the initial tangent direction. Defaults to a fixed seed
        for reproducibility; the result is direction-independent in the generic
        case.

    Returns
    -------
    float
        The estimated largest Lyapunov exponent :math:`\lambda_1` (per
        iteration). Positive indicates chaos; ``<= 0`` a stable fixed point or
        cycle.

    Notes
    -----
    Regression anchors: the Henon map at ``(a, b) = (1.4, 0.3)`` gives
    :math:`\lambda_1 \approx 0.419` (Henon 1976) and the logistic map at
    ``r = 4`` gives :math:`\lambda_1 = \ln 2` exactly.

    References
    ----------
    - G. Benettin, L. Galgani, A. Giorgilli, J.-M. Strelcyn, *Lyapunov
      Characteristic Exponents for smooth dynamical systems and for
      Hamiltonian systems; a method for computing all of them.* Meccanica
      15 (1980), 9-30. DOI 10.1007/BF02128236.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    if rng is None:
        rng = np.random.default_rng(_DISCRETE_TANGENT_SEED)

    x = np.asarray(x0, dtype=np.float64).copy()
    d = x.shape[0]

    for _ in range(n_transient):
        x = np.asarray(step_fn(x), dtype=np.float64)

    v = rng.standard_normal(d)
    v /= np.linalg.norm(v)

    log_sum = 0.0
    counted = 0
    for _ in range(n):
        jac = np.asarray(jacobian_fn(x), dtype=np.float64)
        v = jac @ v
        norm = float(np.linalg.norm(v))
        if norm > 0.0:
            log_sum += np.log(norm)
            v = v / norm
            counted += 1
        else:  # pragma: no cover - tangent collapsed (e.g. a superstable point)
            # A zero stretch means infinite contraction this step; the orbit is
            # on a (super)stable point. Re-seed a tiny tangent and continue.
            v = rng.standard_normal(d)
            v /= np.linalg.norm(v)
        x = np.asarray(step_fn(x), dtype=np.float64)

    if counted == 0:  # pragma: no cover - every step collapsed
        return float("-inf")
    return log_sum / counted


def _finite_diff_jacobian_map(
    step_fn: Callable[[FloatArray], FloatArray],
    y: FloatArray,
    eps: float = 1e-7,
) -> FloatArray:
    """Central-difference Jacobian of a discrete map ``y -> step_fn(y)``.

    The map analogue of :func:`_finite_diff_jacobian` (no time argument).
    ``O(d)`` extra ``step_fn`` evaluations.
    """
    d = y.shape[0]
    jac = np.empty((d, d), dtype=np.float64)
    for i in range(d):
        e = np.zeros(d, dtype=np.float64)
        e[i] = eps
        jac[:, i] = (
            np.asarray(step_fn(y + e), dtype=np.float64)
            - np.asarray(step_fn(y - e), dtype=np.float64)
        ) / (2.0 * eps)
    return jac


def largest_lyapunov_discrete_system(
    system: DiscreteSystem,
    *,
    params: Mapping[str, float] | None = None,
    x0: FloatArray | None = None,
    n: int = 20_000,
    n_transient: int = 1_000,
    rng: np.random.Generator | None = None,
) -> float:
    r"""Largest Lyapunov exponent of a :class:`DiscreteSystem` instance.

    A convenience wrapper around :func:`largest_lyapunov_discrete` that builds
    the ``step_fn`` and ``jacobian_fn`` from a registered map, so the discrete
    estimator (CSC-003) is available "for free" on every shipped map. The
    Jacobian is taken from the map's analytic ``jacobian`` method when it has one
    (e.g. :class:`~chaotic_systems.systems.conradi.ConradiMap`), otherwise a
    central finite-difference Jacobian of ``step`` is used (e.g. the Henon /
    logistic / standard maps, which ship no analytic Jacobian).

    Parameters
    ----------
    system
        Any :class:`~chaotic_systems.core.discrete.DiscreteSystem` instance.
    params
        Parameter overrides; merged with the map's defaults. ``None`` uses the
        map's default parameters.
    x0
        Initial state. ``None`` uses ``system.initial_state``.
    n, n_transient, rng
        Forwarded to :func:`largest_lyapunov_discrete`.

    Returns
    -------
    float
        The estimated largest Lyapunov exponent (per iteration).

    Notes
    -----
    Regression anchors (the proposal's observable for this wire-up): the Henon
    map at ``(a, b) = (1.4, 0.3)`` gives :math:`\lambda_1 \approx 0.419`
    (Henon 1976) and the logistic map at ``r = 4`` gives :math:`\lambda_1 =
    \ln 2` exactly -- both via the finite-difference Jacobian path here.

    References
    ----------
    - G. Benettin et al. (1980), *Meccanica* 15:9, DOI 10.1007/BF02128236
      (the tangent-map estimator).
    - M. Henon (1976), *A two-dimensional mapping with a strange attractor*,
      *Commun. Math. Phys.* 50:69 (the :math:`\lambda_1 \approx 0.419` anchor).
    """
    merged = system.merged_params(params)
    start = (
        np.asarray(system.initial_state, dtype=np.float64)
        if x0 is None
        else np.asarray(x0, dtype=np.float64)
    )

    def step_fn(y: FloatArray) -> FloatArray:
        return system.step(y, **merged)

    analytic = getattr(system, "jacobian", None)
    if callable(analytic):

        def jacobian_fn(y: FloatArray) -> FloatArray:
            return np.asarray(analytic(y, **merged), dtype=np.float64)
    else:

        def jacobian_fn(y: FloatArray) -> FloatArray:
            return _finite_diff_jacobian_map(step_fn, y)

    return largest_lyapunov_discrete(
        step_fn,
        jacobian_fn,
        start,
        n=n,
        n_transient=n_transient,
        rng=rng,
    )


# ---------------------------------------------------------------------------
# Derived diagnostic: Kaplan-Yorke (Lyapunov) dimension.
# ---------------------------------------------------------------------------


def kaplan_yorke_dimension(spectrum: FloatArray) -> float:
    """Kaplan-Yorke (Lyapunov) dimension of an attractor.

    The Kaplan-Yorke conjecture relates the spectrum of Lyapunov
    exponents :math:`\\lambda_1 \\geq \\lambda_2 \\geq \\dots \\geq
    \\lambda_n` of a dissipative dynamical system to the information
    dimension of its attractor by

    .. math::

        D_{KY} = k + \\frac{\\sum_{i=1}^{k} \\lambda_i}{|\\lambda_{k+1}|},

    where :math:`k` is the largest index for which the cumulative sum
    :math:`\\sum_{i=1}^{k} \\lambda_i \\geq 0`. The interpretation is
    geometric: :math:`k` independent stretching directions plus a
    fractional contribution from the next, contracting direction.

    Canonical reference values (Sprott, *Chaos and Time-Series
    Analysis*, Oxford 2003, Table 5.1 and §5.4):

    - Stable fixed point (all :math:`\\lambda_i < 0`): :math:`D_{KY} = 0`.
    - Limit cycle (:math:`\\lambda_1 = 0`, the rest negative):
      :math:`D_{KY} = 1`.
    - Lorenz canonical (:math:`\\lambda \\approx (0.9056, 0, -14.572)`):
      :math:`D_{KY} \\approx 2.062`.
    - 4D Rossler hyperchaos (two positive exponents):
      :math:`D_{KY} > 3`.

    Parameters
    ----------
    spectrum
        Array of Lyapunov exponents in any order; sorted descending
        internally.

    Returns
    -------
    float
        The Kaplan-Yorke dimension. ``0.0`` when no exponent is
        non-negative (fixed-point attractor); ``n`` (the spectrum
        length) when every cumulative sum is non-negative (no
        contracting direction); ``k + fraction`` otherwise.

    Raises
    ------
    ValueError
        If the spectrum is empty.

    References
    ----------
    - J. L. Kaplan, J. A. Yorke, *Chaotic behavior of multidimensional
      difference equations*, LNM 730, Springer (1979), 204-227.
    - J. C. Sprott, *Chaos and Time-Series Analysis*, Oxford 2003,
      sec. 5.
    """
    arr = np.asarray(spectrum, dtype=np.float64)
    if arr.size == 0:
        raise ValueError(
            "kaplan_yorke_dimension requires a non-empty spectrum"
        )
    sorted_desc = np.sort(arr)[::-1]
    cumsum = np.cumsum(sorted_desc)
    # The largest Lyapunov exponent is already negative => fixed point.
    if not bool(cumsum[0] >= 0.0):
        return 0.0
    # k = number of leading entries whose cumulative sum is non-negative.
    k = int(np.sum(cumsum >= 0.0))
    if k >= sorted_desc.size:
        # No contracting direction; report integer dimension n.
        return float(sorted_desc.size)
    next_lambda = float(sorted_desc[k])
    if abs(next_lambda) < 1e-12:
        # Degenerate: cumulative sum tips negative at a near-zero next
        # exponent. The integer-part k is the meaningful answer.
        return float(k)
    cumsum_k = float(cumsum[k - 1])
    return float(k) + cumsum_k / abs(next_lambda)


__all__ = [
    "kaplan_yorke_dimension",
    "largest_lyapunov_discrete",
    "largest_lyapunov_discrete_system",
    "largest_lyapunov_two_trajectory",
    "lyapunov_spectrum",
]
