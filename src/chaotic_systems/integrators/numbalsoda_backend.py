"""Optional ``numbalsoda``-backed LSODA integrator backend (I2).

This module is the I2 milestone from
``docs/proposals/capability-roadmap-2026-05-17.md``. It exposes a
single :class:`~chaotic_systems.integrators._protocol.Integrator`-
protocol instance (``"NumbaLSODA"``) wrapping Wogan et al.'s
``numbalsoda.lsoda`` — a numba-callable LSODA that auto-detects
stiffness (Adams ↔ BDF) and runs the integration loop entirely in
native code. It closes the "you can JIT your RHS but the outer
loop is still Python" gap that ``docs/numerics.md`` explicitly
calls out as a known limitation of the fixed-step JIT recipe.

Optional dependency
-------------------
``numbalsoda`` and ``numba`` ship as the existing ``[performance]``
extra of ``pyproject.toml``. The module imports cleanly when neither
is installed: the :data:`NumbaLSODA` instance can still be queried
for its :attr:`~_protocol.Integrator.name` and registered in the
integrator picker, but calling :meth:`NumbaLSODA.integrate` raises
:class:`ImportError` with a ``pip install -e '.[performance]'``
hint. This is the same pattern the I1 JAX backend uses.

Maintenance status
------------------
``numbalsoda`` v0.3.4 (Sep 2022) is the most recent release. The
package is maintenance-dormant but the underlying ODEPACK LSODA
routine is itself frozen-spec, so the backend remains correct.
Prefer the I1 diffrax / JAX backend
(:mod:`chaotic_systems.integrators.jax_backend`) for new
optional-backend work — it is actively maintained and unlocks
batched ``vmap`` workflows that LSODA cannot.

User-supplied RHS
-----------------
``numbalsoda.lsoda`` runs entirely in numba-compiled native code,
so the right-hand side **must** be a
``numba.cfunc(numbalsoda.lsoda_sig)``-decorated callable with the
signature ``(t, u, du, p) -> None`` (filling ``du`` in place). A
standard Python ``rhs(t, y) -> dy/dt`` callable cannot cross
numbalsoda's Fortran boundary; passing one raises a clear
:class:`TypeError`.

To make the migration painless we ship
:func:`lorenz_numbalsoda_rhs` as the canonical reference: a
five-line cfunc'd Lorenz '63 vector field that matches
:class:`chaotic_systems.systems.Lorenz` to integrator tolerance.
Parameters cross the Fortran boundary via the ``data=`` channel
(``p[0]`` = sigma, ``p[1]`` = rho, ``p[2]`` = beta) so callers can
sweep them without recompiling the cfunc. Other polynomial systems
(Rossler, Duffing, Chua, ...) follow the same recipe — fill ``du``
element-wise from ``u`` and ``p``.

References
----------
- N. Wogan et al., ``numbalsoda`` v0.3.4,
  https://pypi.org/project/numbalsoda/ (Sep 2022). README contains
  the canonical usage example this module mirrors.
- A. C. Hindmarsh, *ODEPACK, a systematized collection of ODE
  solvers*, in *Scientific Computing*, R. S. Stepleman et al.
  (eds.), North-Holland, 1983 — the original LSODA paper.
- E. N. Lorenz, *Deterministic Nonperiodic Flow*, J. Atmos. Sci. 20
  (1963), 130-141 — for :func:`lorenz_numbalsoda_rhs`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from chaotic_systems.core.base import FloatArray, Trajectory
from chaotic_systems.integrators._protocol import RHS

_NUMBALSODA_INSTALL_HINT: str = (
    "NumbaLSODA backend not installed. Install with "
    "`pip install -e '.[performance]'` (adds `numba>=0.60` and "
    "`numbalsoda>=0.3`)."
)

_DEFAULT_MXSTEP: int = 10_000
_DEFAULT_N_POINTS: int = 200


def _import_numbalsoda() -> tuple[Any, Any]:
    """Lazily import numbalsoda + numba and return them.

    Returns ``(numbalsoda, numba)``. Raises :class:`ImportError`
    with the canonical install hint if either package is missing.
    The lazy structure is what keeps the no-numbalsoda cost story
    honest — importing this module does not pay numba's
    multi-second import time.
    """
    try:
        import numba
        import numbalsoda
    except ImportError as exc:  # pragma: no cover - exercised manually
        raise ImportError(_NUMBALSODA_INSTALL_HINT) from exc
    return numbalsoda, numba


def has_numbalsoda_backend() -> bool:
    """Return ``True`` iff numbalsoda + numba can be imported here."""
    try:
        _import_numbalsoda()
    except ImportError:
        return False
    return True


def _resolve_funcptr(rhs: Any) -> int:
    """Coerce a user-supplied ``rhs`` into a numbalsoda function pointer.

    Accepted forms:

    - A ``numba.cfunc(lsoda_sig)``-decorated object exposing
      ``.address`` (the documented numbalsoda contract).
    - A raw integer address (an escape hatch for callers that have
      already extracted ``.address`` elsewhere).

    A standard Python callable (``def rhs(t, y): ...``) cannot be
    passed across numbalsoda's Fortran boundary and is rejected
    with :class:`TypeError` — the error message points at this
    module's docstring for the canonical recipe.
    """
    if isinstance(rhs, int):
        return rhs
    address = getattr(rhs, "address", None)
    if isinstance(address, int):
        return address
    raise TypeError(
        "NumbaLSODA requires a `numba.cfunc(numbalsoda.lsoda_sig)` "
        "callable (with `.address`) or a raw integer address. Got "
        f"{type(rhs).__name__}. See "
        "`chaotic_systems.integrators.numbalsoda_backend` module "
        "docstring for the cfunc recipe."
    )


def _build_t_eval(
    t0: float,
    t1: float,
    *,
    dt: float | None,
    n_points: int | None,
) -> FloatArray:
    """Build the sample grid for the LSODA call.

    Mirrors the scipy-backend convention: ``n_points`` wins over
    ``dt``; if both are ``None`` we fall back to
    :data:`_DEFAULT_N_POINTS` so the caller still gets a usable
    trajectory.
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


@dataclass(slots=True)
class _NumbaLSODA:
    """``numbalsoda.lsoda`` wrapper conforming to the Integrator protocol.

    The single concrete instance is :data:`NumbaLSODA`, registered
    in :mod:`chaotic_systems.integrators` as ``"NumbaLSODA"``.
    """

    name: str

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
        """Integrate a single trajectory through ``numbalsoda.lsoda``.

        Parameters
        ----------
        rhs
            ``numba.cfunc(numbalsoda.lsoda_sig)``-decorated callable
            (or its raw integer ``.address``). A plain Python
            ``rhs(t, y)`` is rejected with :class:`TypeError`; see
            the module docstring for the canonical cfunc recipe.
        t_span, y0, dt, n_points
            Standard
            :class:`~chaotic_systems.integrators._protocol.Integrator`
            arguments.
        rtol, atol
            Tolerances forwarded to ``numbalsoda.lsoda``.
        kwargs
            ``data=`` (ndarray of parameters passed through to the
            cfunc's ``p`` channel) and ``mxstep=`` (max internal
            steps per output interval; defaults to
            :data:`_DEFAULT_MXSTEP`) are honored. Any other kwarg
            surfaces as :class:`TypeError`.

        Returns
        -------
        Trajectory
            ``t`` is the (N,) sample grid, ``y`` is the
            (N, state_dim) state matrix, ``integrator`` is
            :attr:`name`.

        Raises
        ------
        ImportError
            If numbalsoda / numba is not installed.
        TypeError
            If ``rhs`` is not a cfunc / raw address, or if an
            unsupported kwarg was passed.
        RuntimeError
            If numbalsoda reports ``success=False``.
        """
        numbalsoda_mod, _ = _import_numbalsoda()

        data = kwargs.pop("data", None)
        mxstep = int(kwargs.pop("mxstep", _DEFAULT_MXSTEP))
        if kwargs:
            raise TypeError(
                f"{self.name}.integrate received unexpected kwargs: "
                f"{sorted(kwargs)}"
            )

        funcptr = _resolve_funcptr(rhs)

        t0, t1 = float(t_span[0]), float(t_span[1])
        t_eval = _build_t_eval(t0, t1, dt=dt, n_points=n_points)

        y0_arr = np.ascontiguousarray(y0, dtype=np.float64)

        lsoda_kwargs: dict[str, Any] = {
            "rtol": float(rtol),
            "atol": float(atol),
            "mxstep": mxstep,
        }
        if data is not None:
            lsoda_kwargs["data"] = np.ascontiguousarray(data, dtype=np.float64)

        usol, success = numbalsoda_mod.lsoda(
            funcptr, y0_arr, t_eval, **lsoda_kwargs
        )
        if not bool(success):
            raise RuntimeError(
                f"{self.name} integration failed "
                "(numbalsoda.lsoda returned success=False); try "
                "looser tolerances or a larger mxstep."
            )

        return Trajectory(
            t=np.ascontiguousarray(t_eval, dtype=np.float64),
            y=np.ascontiguousarray(usol, dtype=np.float64),
            integrator=self.name,
        )


#: ``NumbaLSODA`` integrator — wraps ``numbalsoda.lsoda``. Auto-
#: detects stiffness via the ODEPACK LSODA Adams/BDF switch, so it
#: is a drop-in replacement for scipy's ``"LSODA"`` when the user
#: has already cfunc'd the RHS.
NumbaLSODA = _NumbaLSODA(name="NumbaLSODA")


# --------------------------------------------------------------------------
# Reference cfunc'd Lorenz RHS used by tests and the docstring pattern.
# Other systems follow the same recipe — fill ``du`` element-wise from
# ``u`` and ``p`` (the parameter channel).
# --------------------------------------------------------------------------


def lorenz_numbalsoda_rhs() -> Any:
    """Return a ``numba.cfunc``-compiled Lorenz '63 vector field.

    The cfunc takes parameters via the numbalsoda ``p`` channel:
    pass ``data=np.array([sigma, rho, beta])`` to
    :meth:`NumbaLSODA.integrate`. Canonical values
    (Lorenz, *J. Atmos. Sci.* 20, 1963) are
    ``(sigma, rho, beta) = (10, 28, 8/3)``.

    The pattern (cfunc body fills ``du`` element-wise from ``u``
    and ``p``) is the same one any polynomial system follows;
    callers should write their own cfuncs in the same shape.
    """
    numbalsoda_mod, numba_mod = _import_numbalsoda()

    @numba_mod.cfunc(numbalsoda_mod.lsoda_sig)
    def rhs(t, u, du, p):  # type: ignore[no-untyped-def]
        du[0] = p[0] * (u[1] - u[0])
        du[1] = u[0] * (p[1] - u[2]) - u[1]
        du[2] = u[0] * u[1] - p[2] * u[2]

    return rhs


__all__ = [
    "NumbaLSODA",
    "has_numbalsoda_backend",
    "lorenz_numbalsoda_rhs",
]
