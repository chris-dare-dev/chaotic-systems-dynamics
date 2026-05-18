"""Optional JAX integrator backend, powered by `diffrax`_.

This module is the I1 milestone from
``docs/proposals/capability-roadmap-2026-05-17.md``. It exposes two
:class:`~chaotic_systems.integrators._protocol.Integrator`-protocol
classes (``JAX-RK45`` / ``JAX-Tsit5``) and a :func:`vmap_trajectories`
helper that runs a *batch* of trajectories in a single JIT-compiled
call. Together they unblock the basin-of-attraction map (D4) and
arbitrary parameter sweeps without invasive changes to the rest of
the codebase.

Optional dependency
-------------------
JAX and diffrax are an **optional extra**. The module imports cleanly
when neither is installed — concrete classes can be constructed and
queried for ``name``, but calling :meth:`JaxRK45.integrate` or
:func:`vmap_trajectories` raises a clear :class:`ImportError` with a
``pip install -e .[jax]`` hint. The deferred-import pattern lives in
:func:`_import_diffrax` below; everything user-facing is structured
around it.

The cost story: this means a baseline ``import chaotic_systems`` does
not pay JAX's multi-second import time. Users who never opt into the
JAX backend are unaffected.

User-supplied RHS
-----------------
The integrator runs ``diffrax.diffeqsolve`` under the hood, which is
designed for *JAX-traceable* right-hand sides — i.e. functions whose
operations all flow through ``jax.numpy``. The numpy-based ``_rhs``
methods on this project's existing :class:`DynamicalSystem` subclasses
will not trace cleanly (``np.array(...)`` blocks JIT). For v1 the
integrator therefore expects the caller to provide a JAX-traceable
``rhs`` callable directly.

To make the migration painless we ship :func:`lorenz_jax_rhs` as the
canonical reference: a 5-line JAX-traceable Lorenz vector field that
matches :class:`chaotic_systems.systems.Lorenz` to integrator
tolerance. The same pattern (replace ``np`` with ``jnp``, return a
``jnp.array``) carries over to every polynomial system the project
ships (Rössler, Duffing, Chua, ...) — see CONTEXT.md for the
follow-up.

References
----------
- P. Kidger, *On Neural Differential Equations*, DPhil thesis, Oxford
  (2021), §5 — original derivation of the diffrax architecture.
- Diffrax documentation, https://docs.kidger.site/diffrax/ — API
  reference; the integrator + vmap patterns implemented here follow
  the "Getting started" and "Patrick's vmap example" tutorials
  verbatim.
- E. N. Lorenz, *Deterministic Nonperiodic Flow*, J. Atmos. Sci. 20
  (1963), 130-141 — for :func:`lorenz_jax_rhs`.

.. _diffrax: https://github.com/patrick-kidger/diffrax
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from chaotic_systems.core.base import FloatArray, Trajectory
from chaotic_systems.integrators._protocol import RHS

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    import diffrax  # noqa: F401

# Cached install hint so every error path surfaces the same exact line.
_JAX_INSTALL_HINT: str = (
    "JAX backend not installed. Install with `pip install -e '.[jax]'` "
    "(adds `jax>=0.4.30` and `diffrax>=0.6`)."
)


def _import_diffrax() -> tuple[Any, Any, Any]:
    """Lazily import diffrax / jax.numpy / jax and return them.

    Returns ``(diffrax, jnp, jax)`` so call sites can pattern-match.
    Raises :class:`ImportError` with the canonical install hint if
    either package is missing. The lazy structure is what keeps the
    no-JAX cost story honest — see this module's docstring.

    Side effect: enables JAX's 64-bit mode (``jax_enable_x64=True``).
    JAX defaults to float32 for accelerator throughput, but at
    float32 precision a tolerance below ~1e-6 is unattainable —
    every diffrax adaptive step fails until ``max_steps`` is hit
    and the solver raises. Scientific ODE work needs float64; we
    set the flag once at import time so callers don't have to
    remember. ``jax.config.update`` is idempotent so a second
    import is a no-op.
    """
    try:
        import diffrax
        import jax
        import jax.numpy as jnp
    except ImportError as exc:  # pragma: no cover - exercised manually
        raise ImportError(_JAX_INSTALL_HINT) from exc
    jax.config.update("jax_enable_x64", True)
    return diffrax, jnp, jax


def has_jax_backend() -> bool:
    """Return ``True`` iff JAX + diffrax can be imported here."""
    try:
        _import_diffrax()
    except ImportError:
        return False
    return True


# diffrax solver-name aliases. Mapping str → diffrax solver class is
# done inside :func:`_resolve_solver` so the class itself is not
# imported at module-load time.
_SUPPORTED_SOLVERS: tuple[str, ...] = ("Tsit5", "Dopri5", "Dopri8")

# Generous default step cap. diffrax ships ``max_steps=4096`` which is
# too tight for tight-tolerance chaotic runs (Lorenz at rtol=1e-10
# over 5 time units already overflows). 100k is enough headroom for
# the longest realistic GUI run (~120 s of integrated time at default
# tolerances) while still tripping fast on a genuinely runaway RHS.
_DEFAULT_MAX_STEPS: int = 100_000


def _resolve_solver(diffrax_mod: Any, name: str) -> Any:
    """Return a diffrax solver *instance* for ``name``.

    Supports ``"Tsit5"`` (Tsitouras 5(4) — diffrax's default), ``"Dopri5"``
    (Dormand-Prince 5(4) — matches scipy ``RK45``), and ``"Dopri8"``
    (matches scipy ``DOP853``).
    """
    if name == "Tsit5":
        return diffrax_mod.Tsit5()
    if name == "Dopri5":
        return diffrax_mod.Dopri5()
    if name == "Dopri8":
        return diffrax_mod.Dopri8()
    raise KeyError(
        f"unknown diffrax solver {name!r}; "
        f"supported: {sorted(_SUPPORTED_SOLVERS)}"
    )


def _run_diffeqsolve(
    rhs: Callable[..., Any],
    t_span: tuple[float, float],
    y0: FloatArray,
    *,
    solver_name: str,
    dt: float | None,
    n_points: int | None,
    rtol: float,
    atol: float,
    args: Any = None,
    max_steps: int = _DEFAULT_MAX_STEPS,
) -> tuple[np.ndarray, np.ndarray]:
    """Single-trajectory call to diffrax's ``diffeqsolve``.

    Returns ``(ts, ys)`` as numpy arrays — ``ts`` shape ``(N,)``,
    ``ys`` shape ``(N, state_dim)``. The caller (integrator class or
    :func:`vmap_trajectories`) decides how to package these.
    """
    diffrax_mod, jnp, _ = _import_diffrax()

    t0, t1 = float(t_span[0]), float(t_span[1])
    if t1 <= t0:
        raise ValueError(
            f"t_span must be increasing (got t0={t0!r}, t1={t1!r})"
        )

    n_p: int
    if n_points is not None:
        n_p = int(n_points)
        if n_p < 2:
            raise ValueError(f"n_points must be >= 2 (got {n_points!r})")
    elif dt is not None:
        if float(dt) <= 0.0:
            raise ValueError(f"dt must be positive (got {dt!r})")
        n_p = max(2, int(round((t1 - t0) / float(dt))) + 1)
    else:
        # Fall back to a reasonable dense default so callers that omit
        # both knobs still get a smooth trajectory.
        n_p = 200

    ts = jnp.linspace(t0, t1, n_p)
    # dt0 must be positive even when the stepsize controller is fully
    # adaptive — it's the initial guess. Use a fraction of t_span.
    dt0 = float(dt) if dt is not None else max((t1 - t0) / 100.0, 1e-6)

    term = diffrax_mod.ODETerm(rhs)
    solver = _resolve_solver(diffrax_mod, solver_name)
    sol = diffrax_mod.diffeqsolve(
        term,
        solver,
        t0,
        t1,
        dt0=dt0,
        y0=jnp.asarray(y0),
        args=args,
        saveat=diffrax_mod.SaveAt(ts=ts),
        stepsize_controller=diffrax_mod.PIDController(rtol=rtol, atol=atol),
        max_steps=int(max_steps),
    )
    return np.asarray(sol.ts), np.asarray(sol.ys)


@dataclass(slots=True)
class _JaxAdaptive:
    """Common JAX integrator wrapper. Subclasses set :attr:`name` /
    :attr:`solver_name`.

    :attr:`name` is the project-side identifier exposed via the
    registry (``"JAX-Tsit5"`` / ``"JAX-RK45"``). :attr:`solver_name`
    is the diffrax-internal solver class name (``"Tsit5"`` /
    ``"Dopri5"`` / ``"Dopri8"``).
    """

    name: str
    solver_name: str

    def integrate(
        self,
        rhs: RHS,
        t_span: tuple[float, float],
        y0: FloatArray,
        *,
        dt: float | None = None,
        n_points: int | None = None,
        rtol: float = 1e-7,
        atol: float = 1e-9,
        **kwargs: Any,
    ) -> Trajectory:
        """Integrate a single trajectory with the JAX backend.

        Parameters
        ----------
        rhs
            **JAX-traceable** vector field ``rhs(t, y)`` or
            ``rhs(t, y, args)`` returning ``dy/dt``. Operations must
            flow through ``jax.numpy``; a numpy-based RHS will fail to
            JIT-trace.
        t_span, y0, dt, n_points
            Standard
            :class:`~chaotic_systems.integrators._protocol.Integrator`
            arguments.
        rtol, atol
            Tolerances for the PID stepsize controller. Defaults are
            looser than the scipy backend's (1e-7 / 1e-9) since
            diffrax's defaults are calibrated for JIT throughput.
        kwargs
            Forwarded ``args=`` may be supplied for diffrax's ``args``
            channel (passed as the third argument to ``rhs``).

        Returns
        -------
        Trajectory
            ``t`` is the (N,) sample grid, ``y`` is the (N, state_dim)
            state matrix, ``integrator`` is :attr:`name`.

        Raises
        ------
        ImportError
            If JAX or diffrax is not installed. Surface with
            ``pip install -e '.[jax]'``.
        """
        args = kwargs.pop("args", None)
        max_steps = int(kwargs.pop("max_steps", _DEFAULT_MAX_STEPS))
        if kwargs:
            raise TypeError(
                f"{self.name}.integrate received unexpected kwargs: "
                f"{sorted(kwargs)}"
            )

        # Adapt a two-argument rhs to diffrax's three-argument signature
        # if the user supplied the simpler form. This keeps the
        # Integrator-protocol promise that ``rhs(t, y)`` works.
        if _arity(rhs) == 2:
            wrapped: Callable[[float, Any, Any], Any] = lambda t, y, _args: rhs(  # noqa: E731
                t, y
            )
        else:
            wrapped = rhs  # type: ignore[assignment]

        ts, ys = _run_diffeqsolve(
            wrapped,
            t_span,
            np.asarray(y0, dtype=np.float64),
            solver_name=self.solver_name,
            dt=dt,
            n_points=n_points,
            rtol=rtol,
            atol=atol,
            args=args,
            max_steps=max_steps,
        )
        return Trajectory(
            t=np.ascontiguousarray(ts, dtype=np.float64),
            y=np.ascontiguousarray(ys, dtype=np.float64),
            integrator=self.name,
        )


def _arity(fn: Callable[..., Any]) -> int:
    """Best-effort positional-parameter count for an RHS callable.

    Falls back to ``3`` if introspection fails — the wrapper in
    :meth:`_JaxAdaptive.integrate` then trusts the user to supply a
    diffrax-style ``(t, y, args)`` signature, which matches diffrax's
    own contract.
    """
    import inspect

    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return 3
    positional = [
        p
        for p in sig.parameters.values()
        if p.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]
    return len(positional)


#: ``JAX-RK45`` integrator — diffrax ``Dopri5`` (Dormand-Prince 5(4)).
#: Numerically equivalent to scipy's ``RK45`` so existing comparison
#: tests stay valid when callers swap the backend.
JaxRK45 = _JaxAdaptive(name="JAX-RK45", solver_name="Dopri5")

#: ``JAX-Tsit5`` integrator — diffrax ``Tsit5`` (Tsitouras 5(4)).
#: diffrax's default; usually slightly faster than ``Dopri5`` per
#: step at the same tolerance.
JaxTsit5 = _JaxAdaptive(name="JAX-Tsit5", solver_name="Tsit5")


# --------------------------------------------------------------------------
# Batched / vmapped trajectory helper.
# --------------------------------------------------------------------------


def vmap_trajectories(
    rhs: Callable[..., Any],
    t_span: tuple[float, float],
    y0_batch: FloatArray,
    *,
    args_batch: Any = None,
    n_points: int = 200,
    solver: str = "Tsit5",
    rtol: float = 1e-7,
    atol: float = 1e-9,
    dt0: float | None = None,
    max_steps: int = _DEFAULT_MAX_STEPS,
) -> tuple[np.ndarray, np.ndarray]:
    """Run a batch of trajectories in one JIT-compiled call.

    This is the function that makes basin-of-attraction maps and
    multi-IC parameter sweeps tractable — instead of 65,536 sequential
    Python integrator calls (a 256×256 basin grid), diffrax + JAX
    fuse the batch into a single XLA kernel.

    Parameters
    ----------
    rhs
        **JAX-traceable** vector field. Either signature works:

        - ``rhs(t, y)`` — for batches where every member shares the
          same parameters (perturbed-IC sweeps, basin maps).
        - ``rhs(t, y, args)`` — when ``args_batch`` is supplied; one
          ``args`` element per batch member.

    t_span
        ``(t0, t1)`` time interval, same for every batch member.
    y0_batch
        Shape ``(B, state_dim)``. The initial conditions to sweep
        over.
    args_batch
        Optional. Either ``None`` (no args broadcast) or a pytree
        whose leaves all have leading dimension ``B``. Forwarded as
        ``args=`` to ``diffrax.diffeqsolve``.
    n_points
        Samples per trajectory.
    solver
        ``"Tsit5"`` / ``"Dopri5"`` / ``"Dopri8"`` — see
        :data:`_SUPPORTED_SOLVERS`.
    rtol, atol
        PID stepsize-controller tolerances.
    dt0
        Initial step-size guess. If ``None``, ``(t1 - t0) / 100``.

    Returns
    -------
    ts, ys
        ``ts`` shape ``(N,)`` — the common time grid.
        ``ys`` shape ``(B, N, state_dim)`` — the batched trajectories.

    Raises
    ------
    ImportError
        If JAX / diffrax is not installed.
    ValueError
        If ``y0_batch`` is not 2-D or shapes don't add up.
    """
    diffrax_mod, jnp, jax = _import_diffrax()

    y0_arr = np.ascontiguousarray(y0_batch, dtype=np.float64)
    if y0_arr.ndim != 2:
        raise ValueError(
            f"y0_batch must be 2-D (B, state_dim); got shape {y0_arr.shape}"
        )
    if y0_arr.shape[0] < 1:
        raise ValueError("y0_batch must contain at least one initial condition")

    t0, t1 = float(t_span[0]), float(t_span[1])
    if t1 <= t0:
        raise ValueError(
            f"t_span must be increasing (got t0={t0!r}, t1={t1!r})"
        )
    if int(n_points) < 2:
        raise ValueError(f"n_points must be >= 2 (got {n_points!r})")

    ts = jnp.linspace(t0, t1, int(n_points))
    effective_dt0 = float(dt0) if dt0 is not None else max((t1 - t0) / 100.0, 1e-6)

    # Adapt 2-arg rhs to diffrax's (t, y, args) form, same as integrate().
    if _arity(rhs) == 2:
        wrapped: Callable[[float, Any, Any], Any] = lambda t, y, _a: rhs(t, y)  # noqa: E731
    else:
        wrapped = rhs  # type: ignore[assignment]

    term = diffrax_mod.ODETerm(wrapped)
    solver_obj = _resolve_solver(diffrax_mod, solver)
    saveat = diffrax_mod.SaveAt(ts=ts)
    stepsize_controller = diffrax_mod.PIDController(rtol=rtol, atol=atol)

    def _solve_one(y0: Any, args: Any) -> Any:
        sol = diffrax_mod.diffeqsolve(
            term,
            solver_obj,
            t0,
            t1,
            dt0=effective_dt0,
            y0=y0,
            args=args,
            saveat=saveat,
            stepsize_controller=stepsize_controller,
            max_steps=int(max_steps),
        )
        return sol.ys

    # vmap over the batch axis of y0 (and args, if supplied).
    if args_batch is None:
        ys = jax.vmap(_solve_one, in_axes=(0, None))(jnp.asarray(y0_arr), None)
    else:
        ys = jax.vmap(_solve_one, in_axes=(0, 0))(
            jnp.asarray(y0_arr), args_batch
        )

    return np.asarray(ts), np.asarray(ys)


# --------------------------------------------------------------------------
# Reference JAX-traceable Lorenz RHS used by tests and the docstring
# pattern. Other systems follow the same recipe — replace ``np`` with
# ``jnp`` and return a ``jnp.array``.
# --------------------------------------------------------------------------


def lorenz_jax_rhs(
    sigma: float = 10.0,
    rho: float = 28.0,
    beta: float = 8.0 / 3.0,
) -> Callable[..., Any]:
    """Return a JAX-traceable Lorenz '63 vector field with fixed params.

    Mirrors :class:`chaotic_systems.systems.Lorenz._rhs` but uses
    ``jax.numpy`` so the result can be JIT-compiled and vmapped over.
    The closure binds the parameters so the returned callable has the
    diffrax-friendly ``rhs(t, y, args)`` signature with ``args``
    unused.
    """
    _, jnp, _ = _import_diffrax()

    def rhs(t: float, y: Any, args: Any = None) -> Any:
        x, y_, z = y[0], y[1], y[2]
        return jnp.array(
            [
                sigma * (y_ - x),
                x * (rho - z) - y_,
                x * y_ - beta * z,
            ]
        )

    return rhs


__all__ = [
    "JaxRK45",
    "JaxTsit5",
    "has_jax_backend",
    "lorenz_jax_rhs",
    "vmap_trajectories",
]
