"""Numba availability shim.

We want the package to work even if ``numba`` is not installed (e.g. in a
minimal install, or on a platform where llvmlite wheels are unavailable).
Modules that want to JIT a hot loop should import :func:`maybe_njit` from
here and use it as a decorator — it behaves like :func:`numba.njit` if
numba is present, and otherwise is the identity decorator (so the function
runs as plain Python / NumPy).

The :data:`NUMBA_AVAILABLE` flag is exported for callers that want to log
which path they took or skip benchmarks that depend on JIT.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

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


__all__ = ["NUMBA_AVAILABLE", "maybe_njit"]
