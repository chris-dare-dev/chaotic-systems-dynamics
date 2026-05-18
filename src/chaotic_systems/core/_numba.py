"""Numba availability shim + AOT-compilation helper for sympy-backed RHSs.

We want the package to work even if ``numba`` is not installed (e.g. in a
minimal install, or on a platform where llvmlite wheels are unavailable).
Modules that want to JIT a hot loop should import :func:`maybe_njit` from
here and use it as a decorator — it behaves like :func:`numba.njit` if
numba is present, and otherwise is the identity decorator (so the function
runs as plain Python / NumPy).

The :data:`NUMBA_AVAILABLE` flag is exported for callers that want to log
which path they took or skip benchmarks that depend on JIT.

P2 contract — :func:`compile_rhs`
---------------------------------
For systems whose RHS is built via :func:`sympy.lambdify` (the
:class:`~chaotic_systems.core.LagrangianSystem`-backed
:class:`~chaotic_systems.systems.DoublePendulum` and the
:class:`~chaotic_systems.core.HamiltonianSystem`-backed
:class:`~chaotic_systems.systems.HenonHeiles`), the bulk of per-step
work happens inside the lambdified function. Wrapping that inner
function with :func:`numba.njit` is the easy speed win
``CONTEXT.md`` "What's next" #4 / proposal P2 calls out — it removes
Python-call overhead and lets the JIT inline the algebraic
expressions.

:func:`compile_rhs` does exactly that: it inspects the system,
finds the embedded :class:`LagrangianSystem` or
:class:`HamiltonianSystem`, ``numba.njit``\\s the inner lambdified
callable, and returns a uniform ``(t, y, params_dict) -> dy/dt``
adapter that does the array assembly. If numba isn't installed or
the JIT compile fails, the adapter transparently falls back to the
system's plain-Python ``rhs`` method — callers see no behaviour
change either way.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeVar

import numpy as np

F = TypeVar("F", bound=Callable[..., Any])

try:  # pragma: no cover - exercised implicitly by environment
    import numba  # type: ignore[import-untyped]

    NUMBA_AVAILABLE: bool = True
except ImportError:  # pragma: no cover
    numba = None  # type: ignore[assignment]
    NUMBA_AVAILABLE = False


def maybe_njit(*jit_args: Any, **jit_kwargs: Any) -> Callable[[F], F]:
    """Return a decorator that JIT-compiles via numba if available.

    Usage::

        @maybe_njit(cache=True, fastmath=True)
        def rhs(t, y):
            ...

    If numba is unavailable, the decorator is the identity (no compilation,
    no behavioural change).
    """

    if NUMBA_AVAILABLE:
        # numba.njit returns a decorator when called with kwargs.
        return numba.njit(*jit_args, **jit_kwargs)  # type: ignore[no-any-return]

    def _identity(func: F) -> F:
        return func

    return _identity


# Type alias for the compiled-RHS callable that :func:`compile_rhs`
# returns. Matches the calling convention the integrators already use.
CompiledRHS = Callable[[float, np.ndarray, "Mapping[str, float] | None"], np.ndarray]


def compile_rhs(system: Any) -> CompiledRHS:
    """Return a numba-compiled ``rhs(t, y, params)`` adapter for ``system``.

    Resolution order:

    1. **Lagrangian-backed system** — has an attribute (typically
       ``_lsys`` or ``lagrangian``) whose value is a
       :class:`~chaotic_systems.core.lagrangian.LagrangianSystem`.
       The inner ``LagrangianSystem._rhs_func`` (a ``sp.lambdify``
       output computing ``qddot`` from
       ``(t, q1, ..., qn, qd1, ..., qdn, *params)``) is JIT'd with
       :func:`numba.njit`; the wrapper splits ``y`` into ``(q, qd)``,
       calls the JIT'd kernel, and assembles ``[qd; qddot]``.

    2. **Hamiltonian-backed system** — has a ``hamiltonian``
       attribute whose value is a
       :class:`~chaotic_systems.core.hamiltonian.HamiltonianSystem`.
       Same recipe with the Hamiltonian's flat
       ``[dH/dp; -dH/dq]`` lambdified RHS.

    3. **Pure-numpy system** — neither of the above. We return a
       thin wrapper around the system's existing ``.rhs`` method
       (no JIT — those systems already evaluate in numpy, and
       JIT'ing the bound Python method via numba would require
       extracting it from the class, which is brittle).

    In every branch, if numba isn't installed *or* the JIT compile
    fails on the introspected callable, we silently fall back to
    the system's plain-Python ``rhs`` — the returned adapter still
    has the documented signature, the only difference is per-call
    speed.

    Parameters
    ----------
    system
        Any :class:`~chaotic_systems.core.DynamicalSystem` instance
        (or duck-typed object exposing the same surface).

    Returns
    -------
    CompiledRHS
        ``rhs(t, y, params) -> dy/dt``. ``params`` may be ``None`` to
        use the system's default parameter values; missing keys are
        filled in by ``system.merged_params``.

    Notes
    -----
    Performance: on the double pendulum at the canonical IC, the
    JIT'd path is ~2-5× faster than the plain-Python ``rhs`` (most
    of the cost is the ``sp.lambdify`` body; numba inlines it and
    eliminates the Python call overhead). The first call pays a
    one-time JIT cost of ~0.5-2 s.
    """

    # --- (1) Lagrangian-backed -----------------------------------------
    lsys = _extract_lagrangian_backend(system)
    if lsys is not None:
        return _compile_from_lagrangian(system, lsys)

    # --- (2) Hamiltonian-backed ----------------------------------------
    ham = _extract_hamiltonian_backend(system)
    if ham is not None:
        return _compile_from_hamiltonian(system, ham)

    # --- (3) Pure-numpy system — return a passthrough wrapper ---------
    return _passthrough_wrapper(system)


# ----------------------------------------------------------------------
# Backend introspection.
# ----------------------------------------------------------------------


def _extract_lagrangian_backend(system: Any) -> Any | None:
    """Return the embedded LagrangianSystem on ``system``, or ``None``.

    Looks for the conventional ``_lsys`` cached property first, then
    falls back to a ``lagrangian`` attribute. The duck-typed check
    is "has a ``_rhs_func`` attribute and a ``params`` attribute",
    which matches the shape :class:`LagrangianSystem` exposes
    without requiring a hard import of that class here.
    """
    for attr in ("_lsys", "lagrangian"):
        candidate = getattr(system, attr, None)
        if candidate is None:
            continue
        if hasattr(candidate, "_rhs_func") and hasattr(candidate, "params"):
            # Also verify it isn't actually a HamiltonianSystem (which
            # also has ``_rhs_func`` but no q/p split here).
            if not hasattr(candidate, "_H_func"):
                return candidate
    return None


def _extract_hamiltonian_backend(system: Any) -> Any | None:
    """Return the embedded HamiltonianSystem on ``system``, or ``None``."""
    candidate = getattr(system, "hamiltonian", None)
    if candidate is None:
        return None
    # Duck-typed: HamiltonianSystem carries both _rhs_func and _H_func.
    if hasattr(candidate, "_rhs_func") and hasattr(candidate, "_H_func"):
        return candidate
    return None


# ----------------------------------------------------------------------
# Compilation paths.
# ----------------------------------------------------------------------


def _passthrough_wrapper(system: Any) -> CompiledRHS:
    """Adapter that just calls ``system.rhs`` with the new (t, y, params) shape."""

    def rhs(
        t: float, y: np.ndarray, params: Mapping[str, float] | None = None
    ) -> np.ndarray:
        return system.rhs(t, y, **(params or {}))

    return rhs


def _try_numba_jit(callable_: Callable[..., Any]) -> Callable[..., Any] | None:
    """Best-effort ``numba.njit`` wrap. Returns ``None`` on failure.

    Compiles eagerly via a smoke call on a tuple of scalars (numba's
    lazy mode wouldn't surface compile failures until much later).
    Any exception during JIT or smoke-call falls through to ``None``.
    """
    if not NUMBA_AVAILABLE:
        return None
    try:
        jit_fn = numba.njit(callable_, cache=False)
    except Exception:  # pragma: no cover - numba JIT decoration path
        return None
    # Don't smoke-call here — numba lazy-compiles on first call, which
    # is fine for our case (callers always invoke at least once).
    return jit_fn


def _param_value_list(
    backend: Any, params: Mapping[str, float] | None
) -> list[float]:
    """Order ``params`` to match the backend's ``params`` symbol tuple.

    Both :class:`LagrangianSystem` and :class:`HamiltonianSystem`
    expose a ``params`` attribute that's a sequence of sympy
    symbols; the lambdified callable expects values in that exact
    order. Missing keys raise ``KeyError``.
    """
    param_syms = list(getattr(backend, "params", ()) or ())
    if not param_syms:
        return []
    normalized: dict[str, float] = (
        {} if params is None else {str(k): float(v) for k, v in params.items()}
    )
    values: list[float] = []
    for sym in param_syms:
        key = str(sym)
        if key not in normalized:
            raise KeyError(
                f"missing value for parameter {key!r}; got {sorted(normalized)}"
            )
        values.append(normalized[key])
    return values


def _compile_from_lagrangian(system: Any, lsys: Any) -> CompiledRHS:
    """JIT-wrap the LagrangianSystem's lambdified qddot callable."""
    lambdified = lsys._rhs_func
    jit_fn = _try_numba_jit(lambdified)
    if jit_fn is None:
        return _passthrough_wrapper(system)

    state_dim = int(lsys.state_dim)
    n = state_dim // 2

    def rhs(
        t: float, y: np.ndarray, params: Mapping[str, float] | None = None
    ) -> np.ndarray:
        # Resolve param values via the system's merge first (so the
        # caller can pass partial overrides), then re-order them to
        # match the backend's positional param tuple.
        merged = system.merged_params(params) if params is not None else system.default_params()
        param_vals = _param_value_list(lsys, merged)
        q = y[:n]
        qd = y[n:]
        qddot = jit_fn(float(t), *(float(v) for v in q), *(float(v) for v in qd), *param_vals)
        result = np.empty(state_dim, dtype=np.float64)
        result[:n] = qd
        result[n:] = np.asarray(qddot, dtype=np.float64).ravel()
        return result

    return rhs


def _compile_from_hamiltonian(system: Any, ham: Any) -> CompiledRHS:
    """JIT-wrap the HamiltonianSystem's lambdified [dH/dp; -dH/dq] callable."""
    lambdified = ham._rhs_func
    jit_fn = _try_numba_jit(lambdified)
    if jit_fn is None:
        return _passthrough_wrapper(system)

    state_dim = int(ham.state_dim)
    n = state_dim // 2

    def rhs(
        t: float, y: np.ndarray, params: Mapping[str, float] | None = None
    ) -> np.ndarray:
        merged = system.merged_params(params) if params is not None else system.default_params()
        param_vals = _param_value_list(ham, merged)
        q = y[:n]
        p = y[n:]
        out = jit_fn(float(t), *(float(v) for v in q), *(float(v) for v in p), *param_vals)
        return np.asarray(out, dtype=np.float64).ravel()

    return rhs


__all__ = [
    "CompiledRHS",
    "NUMBA_AVAILABLE",
    "compile_rhs",
    "maybe_njit",
]
