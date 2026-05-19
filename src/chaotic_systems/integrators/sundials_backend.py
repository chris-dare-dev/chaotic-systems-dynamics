"""Optional ``scikit-sundae`` CVODE + IDA integrator backend (I3).

This module is the I3 milestone from
``docs/proposals/capability-roadmap-2026-05-17.md``. It exposes
production-grade SUNDIALS integrators:

- :data:`CVODE` — multistep BDF (default for stiff problems), the
  industry-standard alternative to scipy's ``Radau`` / ``BDF``.
- :data:`CVODEAdams` — multistep Adams-Moulton (non-stiff variant
  of CVODE), the predictor-corrector counterpart of LSODA when
  stiffness is not expected.
- :data:`IDA` — a DAE solver (index-1 differential-algebraic
  equations) for Chua-like piecewise systems and any future
  hidden-constraint formulation. *Not* registered in the standard
  integrator registry because its ``integrate`` signature requires
  a residual function + initial ``yp0``, not a plain ODE RHS.

Optional dependency
-------------------
``scikit-sundae`` ships as the new ``[sundials]`` extra of
``pyproject.toml``. The wheels bundle SUNDIALS 7.5 natively (no
user compile), so the brief's "no Julia / Rust / C++ deps the
user would need to compile" constraint is satisfied. The module
imports cleanly when the extra is absent; only the ``integrate``
methods pull ``sksundae`` in, raising :class:`ImportError` with
the canonical ``pip install -e '.[sundials]'`` hint.

RHS adapter
-----------
``sksundae.cvode.CVODE`` expects ``rhsfn(t, y, yp) -> None``
filling ``yp`` in place; the standard project ``rhs(t, y) -> dy/dt``
returning a new array is auto-adapted at :meth:`CVODE.integrate`
call time. Either signature works — see :func:`_make_rhsfn`.

For IDA the residual ``resfn(t, y, yp, res) -> None`` is the only
supported shape, since DAE residuals fundamentally have no
``return``-style equivalent.

References
----------
- C. R. Wood, S. Bahmani, P. C. Nelson, S. C. Decaluwe, M. R.
  Shaner, *scikit-sundae*, NREL, v1.1.3 (Mar 2026) —
  https://pypi.org/project/scikit-sundae/. README + API docs
  contain the canonical usage example this module mirrors.
- A. C. Hindmarsh et al., *SUNDIALS: Suite of nonlinear and
  differential/algebraic equation solvers*, ACM Trans. Math. Softw.
  31 (2005), 363-396 — the original SUNDIALS paper that CVODE and
  IDA descend from.
- H. H. Robertson, *The solution of a set of reaction rate
  equations*, in J. Walsh (ed.), *Numerical Analysis: An
  Introduction*, Academic Press 1966 — the canonical stiff DAE
  reference problem used by :func:`robertson_residual`.
- E. N. Lorenz, *Deterministic Nonperiodic Flow*, J. Atmos. Sci. 20
  (1963), 130-141 — for :func:`lorenz_sundials_rhsfn`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from chaotic_systems.core.base import FloatArray, Trajectory
from chaotic_systems.integrators._protocol import RHS

_SUNDIALS_INSTALL_HINT: str = (
    "scikit-sundae backend not installed. Install with "
    "`pip install -e '.[sundials]'` (adds `scikit-sundae>=1.1`, "
    "which bundles SUNDIALS 7.5 wheels — no user compile)."
)

_DEFAULT_N_POINTS: int = 200
_DEFAULT_MAX_NUM_STEPS: int = 100_000

# Robertson's canonical stiff DAE constants (Robertson 1966, eq. 1):
#
#     y0' = -k1 y0 + k3 y1 y2
#     y1' =  k1 y0 - k2 y1^2 - k3 y1 y2
#     0   = y0 + y1 + y2 - 1
#
# Conventional rate constants from Hairer-Wanner II §IV.1; widely
# used as the smoke-test DAE in the SUNDIALS, ODEPACK, and DASSL
# test suites.
ROBERTSON_K1: float = 0.04
ROBERTSON_K2: float = 3.0e7
ROBERTSON_K3: float = 1.0e4


def _import_sksundae() -> Any:
    """Lazily import :mod:`sksundae` and return the module.

    Raises :class:`ImportError` with the canonical install hint if
    the package is missing. The lazy structure is what keeps the
    no-sundae cost story honest — importing this module does not
    pay the SUNDIALS wheel's startup cost.
    """
    try:
        import sksundae
    except ImportError as exc:  # pragma: no cover - exercised manually
        raise ImportError(_SUNDIALS_INSTALL_HINT) from exc
    return sksundae


def has_sundials_backend() -> bool:
    """Return ``True`` iff ``sksundae`` can be imported here."""
    try:
        _import_sksundae()
    except ImportError:
        return False
    return True


def _build_tspan(
    t0: float,
    t1: float,
    *,
    dt: float | None,
    n_points: int | None,
) -> FloatArray:
    """Build the dense output grid for ``solve(tspan, ...)``.

    Mirrors the scipy-backend convention: ``n_points`` wins over
    ``dt``; if both are ``None`` we fall back to
    :data:`_DEFAULT_N_POINTS`. ``sksundae``'s solve() treats a
    length-2 ``tspan`` as "internal steps only" — we always build a
    length-N grid so the returned trajectory has a predictable shape.
    """
    if t1 <= t0:
        raise ValueError(
            f"t_span must be increasing (got t0={t0!r}, t1={t1!r})"
        )
    if n_points is not None:
        n_p = int(n_points)
        if n_p < 2:
            raise ValueError(f"n_points must be >= 2 (got {n_points!r})")
        return np.linspace(t0, t1, n_p, dtype=np.float64)
    if dt is not None:
        if float(dt) <= 0.0:
            raise ValueError(f"dt must be positive (got {dt!r})")
        n_p = max(2, int(round((t1 - t0) / float(dt))) + 1)
        return np.linspace(t0, t1, n_p, dtype=np.float64)
    return np.linspace(t0, t1, _DEFAULT_N_POINTS, dtype=np.float64)


def _make_rhsfn(rhs: RHS) -> Callable[[float, Any, Any], None]:
    """Adapt a standard ``rhs(t, y) -> dy/dt`` to sksundae's
    in-place ``rhsfn(t, y, yp) -> None`` shape.

    If ``rhs`` already has the in-place signature (i.e. it accepts
    three positional arguments) we pass it through unchanged.
    Otherwise we wrap the returned numpy array into ``yp[:]`` so
    callers don't have to learn a new RHS convention to use CVODE.
    """
    import inspect

    try:
        sig = inspect.signature(rhs)
        positional = [
            p
            for p in sig.parameters.values()
            if p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        arity = len(positional)
    except (TypeError, ValueError):
        arity = 2  # safest assumption — wrap

    if arity >= 3:
        return rhs  # type: ignore[return-value]

    def rhsfn(t: float, y: Any, yp: Any) -> None:
        yp[:] = rhs(t, y)

    return rhsfn


@dataclass(slots=True)
class _CVODE:
    """``sksundae.cvode.CVODE`` wrapper conforming to the Integrator
    protocol. The concrete instances are :data:`CVODE` (BDF) and
    :data:`CVODEAdams` (Adams-Moulton).

    The ``method`` attribute selects the multistep family:
    ``"BDF"`` for stiff problems (default), ``"Adams"`` for
    non-stiff. Both descend from SUNDIALS CVODE.
    """

    name: str
    method: str  # "BDF" | "Adams"

    def integrate(
        self,
        rhs: RHS,
        t_span: tuple[float, float],
        y0: FloatArray,
        *,
        dt: float | None = None,
        n_points: int | None = None,
        rtol: float = 1e-8,
        atol: float = 1e-10,
        **kwargs: Any,
    ) -> Trajectory:
        """Integrate a single trajectory through ``sksundae.cvode.CVODE``.

        Parameters
        ----------
        rhs
            Vector field. Either signature works:

            - ``rhs(t, y) -> dy/dt`` (the project default) — auto-
              adapted via :func:`_make_rhsfn`.
            - ``rhsfn(t, y, yp) -> None`` (sksundae's native form,
              filling ``yp`` in place).
        t_span, y0, dt, n_points
            Standard
            :class:`~chaotic_systems.integrators._protocol.Integrator`
            arguments. We always materialize a dense ``tspan`` of
            ``n_points`` (or ``dt``-derived) samples — sksundae's
            length-2 ``tspan`` "internal-step" mode is not exposed.
        rtol, atol
            Tolerances forwarded to the CVODE constructor. Defaults
            are tighter than sksundae's library defaults (1e-5 /
            1e-6) so behavior matches the rest of this project's
            integrators on chaotic systems.
        kwargs
            Forwarded ``linsolver=`` / ``max_num_steps=`` /
            ``first_step=`` / ``min_step=`` / ``max_step=`` /
            ``jacfn=`` are honored. Any other kwarg surfaces as
            :class:`TypeError`.

        Returns
        -------
        Trajectory
            ``t`` is the (N,) tspan grid, ``y`` is the
            (N, state_dim) state matrix, ``integrator`` is
            :attr:`name`.

        Raises
        ------
        ImportError
            If scikit-sundae is not installed.
        TypeError
            If an unsupported kwarg is passed.
        RuntimeError
            If sksundae reports a failed integration.
        """
        sksundae = _import_sksundae()

        allowed = {
            "linsolver",
            "max_num_steps",
            "first_step",
            "min_step",
            "max_step",
            "max_order",
            "jacfn",
        }
        extra: dict[str, Any] = {}
        for k in list(kwargs):
            if k in allowed:
                extra[k] = kwargs.pop(k)
        if kwargs:
            raise TypeError(
                f"{self.name}.integrate received unexpected kwargs: "
                f"{sorted(kwargs)}"
            )
        extra.setdefault("max_num_steps", _DEFAULT_MAX_NUM_STEPS)

        t0, t1 = float(t_span[0]), float(t_span[1])
        tspan = _build_tspan(t0, t1, dt=dt, n_points=n_points)
        y0_arr = np.ascontiguousarray(y0, dtype=np.float64)

        rhsfn = _make_rhsfn(rhs)
        solver = sksundae.cvode.CVODE(
            rhsfn,
            method=self.method,
            rtol=float(rtol),
            atol=float(atol),
            **extra,
        )
        soln = solver.solve(tspan, y0_arr)
        if not bool(getattr(soln, "success", True)):
            raise RuntimeError(
                f"{self.name} integration failed: "
                f"{getattr(soln, 'message', 'unknown error')!r} "
                f"(status={getattr(soln, 'status', None)!r})"
            )

        return Trajectory(
            t=np.ascontiguousarray(soln.t, dtype=np.float64),
            y=np.ascontiguousarray(soln.y, dtype=np.float64),
            integrator=self.name,
        )


#: ``CVODE`` integrator — SUNDIALS BDF multistep solver (default for
#: stiff systems). Drop-in alternative to scipy's ``Radau`` / ``BDF``.
CVODE = _CVODE(name="CVODE", method="BDF")

#: ``CVODEAdams`` integrator — SUNDIALS CVODE with Adams-Moulton.
#: Predictor-corrector multistep for non-stiff problems; pairs with
#: ``CVODE`` the way scipy's ``LSODA`` Adams/BDF auto-switch does,
#: minus the auto-switch (the user picks one).
CVODEAdams = _CVODE(name="CVODE-Adams", method="Adams")


# --------------------------------------------------------------------------
# IDA — DAE solver wrapper. Not registered in the standard ODE-only
# integrator registry; consumers call :func:`ida_solve` directly.
# --------------------------------------------------------------------------


IDAResidual = Callable[[float, Any, Any, Any], None]
"""DAE residual signature: ``resfn(t, y, yp, res) -> None``, filling
``res`` in place with ``F(t, y, yp)``."""


def ida_solve(
    resfn: IDAResidual,
    t_span: tuple[float, float],
    y0: FloatArray,
    yp0: FloatArray,
    *,
    algebraic_idx: list[int] | None = None,
    calc_initcond: str | None = "yp0",
    n_points: int = _DEFAULT_N_POINTS,
    rtol: float = 1e-8,
    atol: float = 1e-10,
    **kwargs: Any,
) -> Trajectory:
    """Integrate a DAE through ``sksundae.ida.IDA``.

    Parameters
    ----------
    resfn
        Residual function ``resfn(t, y, yp, res) -> None``, filling
        ``res`` with ``F(t, y, yp)``. A zero residual at every
        integration step is what IDA enforces.
    t_span
        ``(t0, t1)`` interval.
    y0, yp0
        Initial state and its derivative. If ``calc_initcond`` is
        ``"yp0"`` (default) IDA corrects ``yp0`` from a guess; with
        ``"y0"`` it corrects ``y0`` from a guess; with ``None`` the
        user-supplied pair must already be consistent.
    algebraic_idx
        Indices of purely algebraic (non-differential) state
        variables. Required when the DAE has algebraic equations
        (index >= 1).
    calc_initcond
        Initial-condition correction mode — see the sksundae docs.
    n_points, rtol, atol
        As for CVODE.
    kwargs
        Forwarded ``linsolver=`` / ``max_num_steps=`` / etc. as for
        :meth:`_CVODE.integrate`.

    Returns
    -------
    Trajectory
        ``y`` is the (N, state_dim) state matrix; the corresponding
        ``yp`` series is discarded (callers wanting it should call
        ``sksundae.ida.IDA`` directly).

    Notes
    -----
    The DAE solver does not satisfy the standard ODE
    :class:`~chaotic_systems.integrators._protocol.Integrator`
    protocol (residual + ``yp0``); it is exposed as a free
    function rather than a registered integrator so the GUI's
    integrator picker stays purely-ODE.
    """
    sksundae = _import_sksundae()

    allowed = {
        "linsolver",
        "max_num_steps",
        "first_step",
        "min_step",
        "max_step",
        "max_order",
        "jacfn",
        "constraints_idx",
        "constraints_type",
    }
    extra: dict[str, Any] = {}
    for k in list(kwargs):
        if k in allowed:
            extra[k] = kwargs.pop(k)
    if kwargs:
        raise TypeError(
            f"ida_solve received unexpected kwargs: {sorted(kwargs)}"
        )
    extra.setdefault("max_num_steps", _DEFAULT_MAX_NUM_STEPS)

    t0, t1 = float(t_span[0]), float(t_span[1])
    tspan = _build_tspan(t0, t1, dt=None, n_points=n_points)
    y0_arr = np.ascontiguousarray(y0, dtype=np.float64)
    yp0_arr = np.ascontiguousarray(yp0, dtype=np.float64)

    solver = sksundae.ida.IDA(
        resfn,
        algebraic_idx=algebraic_idx,
        calc_initcond=calc_initcond,
        rtol=float(rtol),
        atol=float(atol),
        **extra,
    )
    soln = solver.solve(tspan, y0_arr, yp0_arr)
    if not bool(getattr(soln, "success", True)):
        raise RuntimeError(
            "IDA integration failed: "
            f"{getattr(soln, 'message', 'unknown error')!r} "
            f"(status={getattr(soln, 'status', None)!r})"
        )
    return Trajectory(
        t=np.ascontiguousarray(soln.t, dtype=np.float64),
        y=np.ascontiguousarray(soln.y, dtype=np.float64),
        integrator="IDA",
    )


# --------------------------------------------------------------------------
# Reference RHS / residual callables used by tests and the docstring
# pattern. Other systems follow the same recipe.
# --------------------------------------------------------------------------


def lorenz_sundials_rhsfn(
    sigma: float = 10.0,
    rho: float = 28.0,
    beta: float = 8.0 / 3.0,
) -> Callable[[float, Any, Any], None]:
    """Return a sksundae-native in-place Lorenz '63 vector field.

    Mirrors :class:`chaotic_systems.systems.Lorenz._rhs` but fills
    ``yp`` in place per the CVODE contract instead of returning a
    new array. The default ``(sigma, rho, beta) = (10, 28, 8/3)``
    is Lorenz 1963's canonical chaotic regime.
    """

    def rhsfn(t: float, y: Any, yp: Any) -> None:
        yp[0] = sigma * (y[1] - y[0])
        yp[1] = y[0] * (rho - y[2]) - y[1]
        yp[2] = y[0] * y[1] - beta * y[2]

    return rhsfn


def robertson_residual(
    t: float, y: Any, yp: Any, res: Any
) -> None:
    """IDA-style residual for Robertson's stiff chemical-kinetics DAE.

    The system (Robertson 1966) is

    .. code::

        y0' = -k1 y0 + k3 y1 y2
        y1' =  k1 y0 - k2 y1^2 - k3 y1 y2
        0   = y0 + y1 + y2 - 1

    with rate constants :data:`ROBERTSON_K1`, :data:`ROBERTSON_K2`,
    :data:`ROBERTSON_K3`. Two differential equations + one algebraic
    conservation law — the canonical index-1 DAE smoke test for
    SUNDIALS, ODEPACK, and DASSL.
    """
    res[0] = yp[0] + ROBERTSON_K1 * y[0] - ROBERTSON_K3 * y[1] * y[2]
    res[1] = (
        yp[1]
        - ROBERTSON_K1 * y[0]
        + ROBERTSON_K2 * y[1] * y[1]
        + ROBERTSON_K3 * y[1] * y[2]
    )
    res[2] = y[0] + y[1] + y[2] - 1.0


__all__ = [
    "CVODE",
    "CVODEAdams",
    "IDAResidual",
    "ROBERTSON_K1",
    "ROBERTSON_K2",
    "ROBERTSON_K3",
    "has_sundials_backend",
    "ida_solve",
    "lorenz_sundials_rhsfn",
    "robertson_residual",
]
