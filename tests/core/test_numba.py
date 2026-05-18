"""Tests for the numba shim + :func:`compile_rhs` AOT helper (P2).

The headline contract is **numerical equivalence**: the
:func:`compile_rhs`-returned callable must produce the same
``dy/dt`` as the system's plain-Python ``.rhs`` at every test point,
to machine precision. The JIT path is a pure speed optimization; if
numba is unavailable or the JIT compile fails, the wrapper falls
back to the system's ``.rhs`` transparently and the equivalence
still holds.

Coverage:

- DoublePendulum (LagrangianSystem-backed) at the canonical IC and
  at a grid of random states + parameter perturbations.
- HenonHeiles (HamiltonianSystem-backed) at the canonical IC and
  at random states.
- Lorenz / Rossler / Kuramoto (pure-numpy) — passthrough wrapper
  produces identical outputs.
- ``maybe_njit`` decorator round-trip (legacy contract preserved).
- ``NUMBA_AVAILABLE`` flag is a real bool.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.core import (
    NUMBA_AVAILABLE,
    compile_rhs,
    maybe_njit,
)
from chaotic_systems.systems import (
    DoublePendulum,
    HenonHeiles,
    Kuramoto,
    Lorenz,
    Rossler,
)

# --- Numba shim sanity ----------------------------------------------------


def test_numba_available_flag_is_bool() -> None:
    assert isinstance(NUMBA_AVAILABLE, bool)


def test_maybe_njit_returns_decorator_round_trip() -> None:
    """``maybe_njit`` must always return a callable decorator that, applied
    to a function, returns *something* callable with the same signature."""

    @maybe_njit(cache=False)
    def add(a: float, b: float) -> float:
        return a + b

    assert add(2.0, 3.0) == 5.0


# --- LagrangianSystem-backed: DoublePendulum -----------------------------


def test_compile_rhs_double_pendulum_matches_at_canonical_ic() -> None:
    dp = DoublePendulum()
    fast = compile_rhs(dp)
    y = dp.initial_state.copy()
    ref = dp.rhs(0.0, y)
    got = fast(0.0, y, dp.default_params())
    assert got.shape == ref.shape
    np.testing.assert_allclose(got, ref, atol=1e-12)


def test_compile_rhs_double_pendulum_matches_on_random_grid() -> None:
    dp = DoublePendulum()
    fast = compile_rhs(dp)
    rng = np.random.default_rng(0)
    base = dp.default_params()
    for _ in range(20):
        # Sample a state in a sensible range; keep angles bounded so the
        # double pendulum doesn't try to evaluate at extreme phases.
        y = rng.uniform(-2.0, 2.0, size=4)
        params = {
            k: float(rng.uniform(max(p, 0.5), p * 1.5))
            for k, p in base.items()
        }
        ref = dp.rhs(0.0, y, **params)
        got = fast(0.0, y, params)
        np.testing.assert_allclose(got, ref, atol=1e-10, rtol=1e-10)


def test_compile_rhs_double_pendulum_with_default_params() -> None:
    """``params=None`` uses the system's defaults exactly."""
    dp = DoublePendulum()
    fast = compile_rhs(dp)
    y = dp.initial_state.copy()
    np.testing.assert_allclose(
        fast(0.0, y, None), dp.rhs(0.0, y), atol=1e-12
    )


def test_compile_rhs_double_pendulum_rejects_missing_params() -> None:
    """Partial parameter dict with unknown key raises through merged_params."""
    dp = DoublePendulum()
    fast = compile_rhs(dp)
    y = dp.initial_state.copy()
    with pytest.raises(KeyError, match="Unknown parameter"):
        fast(0.0, y, {"bogus": 1.0})


# --- HamiltonianSystem-backed: HenonHeiles -------------------------------


def test_compile_rhs_henon_heiles_matches_at_canonical_ic() -> None:
    hh = HenonHeiles()
    fast = compile_rhs(hh)
    y = hh.initial_state.copy()
    ref = hh.rhs(0.0, y)
    got = fast(0.0, y, hh.default_params())
    np.testing.assert_allclose(got, ref, atol=1e-12)


def test_compile_rhs_henon_heiles_matches_on_random_grid() -> None:
    hh = HenonHeiles()
    fast = compile_rhs(hh)
    rng = np.random.default_rng(1)
    for _ in range(20):
        y = rng.uniform(-0.5, 0.5, size=4)
        ref = hh.rhs(0.0, y)
        got = fast(0.0, y, hh.default_params())
        np.testing.assert_allclose(got, ref, atol=1e-10, rtol=1e-10)


# --- Pure-numpy passthrough ----------------------------------------------


@pytest.mark.parametrize(
    "system_cls",
    [Lorenz, Rossler, Kuramoto],
    ids=["Lorenz", "Rossler", "Kuramoto"],
)
def test_compile_rhs_passthrough_matches_plain_rhs(system_cls) -> None:  # type: ignore[no-untyped-def]
    """Pure-numpy systems use the passthrough wrapper; output must be exact."""
    sys = system_cls()
    fast = compile_rhs(sys)
    y = sys.initial_state.copy()
    ref = sys.rhs(0.0, y)
    got = fast(0.0, y, sys.default_params())
    np.testing.assert_array_equal(got, ref)


def test_compile_rhs_callable_signature_uniform() -> None:
    """Every compiled adapter accepts (t, y, params=None)."""
    dp = DoublePendulum()
    lor = Lorenz()
    hh = HenonHeiles()
    for sys in (dp, lor, hh):
        fast = compile_rhs(sys)
        # Must be callable with positional t, y, and either no params
        # or a params dict.
        out_default = fast(0.0, sys.initial_state, None)
        out_explicit = fast(0.0, sys.initial_state, sys.default_params())
        np.testing.assert_allclose(out_default, out_explicit, atol=1e-12)


# --- Pure-numpy systems aren't wrongly detected as sympy-backed ---------


def test_lorenz_is_not_classified_as_lagrangian_or_hamiltonian() -> None:
    """The backend introspector must not false-positive on simple ODEs."""
    from chaotic_systems.core._numba import (
        _extract_hamiltonian_backend,
        _extract_lagrangian_backend,
    )

    lor = Lorenz()
    assert _extract_lagrangian_backend(lor) is None
    assert _extract_hamiltonian_backend(lor) is None


def test_double_pendulum_is_classified_as_lagrangian() -> None:
    from chaotic_systems.core._numba import _extract_lagrangian_backend

    dp = DoublePendulum()
    backend = _extract_lagrangian_backend(dp)
    assert backend is not None
    # And it's not misclassified as a Hamiltonian.
    from chaotic_systems.core._numba import _extract_hamiltonian_backend

    assert _extract_hamiltonian_backend(dp) is None


def test_henon_heiles_is_classified_as_hamiltonian() -> None:
    from chaotic_systems.core._numba import _extract_hamiltonian_backend

    hh = HenonHeiles()
    backend = _extract_hamiltonian_backend(hh)
    assert backend is not None
