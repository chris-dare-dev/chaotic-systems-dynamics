"""Parity tests for the JAX-traceable polynomial RHS factories (CSC-027).

Pins the JAX backend's ``<system>_jax_rhs`` factory functions against
the corresponding numpy ``DynamicalSystem._rhs`` to machine precision.
This is the contract that unblocks the I1 JAX backend (and the D4
JAX basin path) for every polynomial system the project ships — until
this lands, only ``Lorenz`` had a JAX-traceable RHS, so any
``vmap_trajectories`` or ``basin_diagram(backend='jax')`` call on
Rossler / Chua / Duffing / RosslerHyper would fail to JIT-trace.

The observable mirrors the P2 numba-RHS parity contract (CONTEXT.md
commit ``28bd53b``): at the canonical default IC and across a 20-point
random grid of ``(state, t)`` pairs, the JAX RHS output must equal the
numpy ``_rhs`` output. We compare with ``rtol=0`` and a small absolute
floor that absorbs float32-vs-float64 JIT casts on platforms where
diffrax defaults to float32 — the structure is exact; the floor only
exists because JAX's ``jnp.array(...)`` may downcast on hardware where
the user has not opted into ``jax.config.update('jax_enable_x64', True)``.

Tests are gated on the ``[jax]`` extra; contributors without it see
the module skipped.
"""

from __future__ import annotations

import numpy as np
import pytest

# Gate the whole module on the optional extra.
pytest.importorskip("jax")
pytest.importorskip("diffrax")

from chaotic_systems.integrators.jax_backend import (
    chua_jax_rhs,
    duffing_jax_rhs,
    lorenz_jax_rhs,
    rossler_hyper_jax_rhs,
    rossler_jax_rhs,
)
from chaotic_systems.systems.chua import Chua
from chaotic_systems.systems.duffing import Duffing
from chaotic_systems.systems.lorenz import Lorenz
from chaotic_systems.systems.rossler import Rossler
from chaotic_systems.systems.rossler_hyper import RosslerHyper

# Tight absolute floor that survives any float32-default downcast diffrax
# may apply when ``jax_enable_x64`` is not set; with x64 enabled the
# error collapses to 0. Same pattern as the P2 numba-RHS parity test.
_PARITY_ATOL: float = 1e-6
_RANDOM_GRID_SIZE: int = 20
_RANDOM_T_MAX: float = 5.0
_RANDOM_SEED: int = 0xC0FFEE


def _to_numpy(jax_array) -> np.ndarray:  # type: ignore[no-untyped-def]
    """Coerce a JAX array to a CPU numpy array for direct comparison."""

    return np.asarray(jax_array)


# ---------------------------------------------------------------------------
# Per-system parity matrix.
# ---------------------------------------------------------------------------
# (system_class, jax_factory, params_at_defaults). Each entry is one
# parametrize case; pytest reports per-system pass/fail.
_PARITY_CASES = [
    pytest.param(Lorenz, lorenz_jax_rhs, id="lorenz"),
    pytest.param(Rossler, rossler_jax_rhs, id="rossler"),
    pytest.param(Chua, chua_jax_rhs, id="chua"),
    pytest.param(Duffing, duffing_jax_rhs, id="duffing"),
    pytest.param(RosslerHyper, rossler_hyper_jax_rhs, id="rossler_hyper"),
]


@pytest.mark.parametrize("system_cls, jax_factory", _PARITY_CASES)
def test_jax_rhs_matches_numpy_rhs_at_canonical_ic(
    system_cls,  # type: ignore[no-untyped-def]
    jax_factory,  # type: ignore[no-untyped-def]
) -> None:
    """At the system's canonical IC, JAX RHS == numpy RHS."""

    system = system_cls()
    default_params = {k: p.default for k, p in system.parameters.items()}
    rhs_jax = jax_factory(**default_params)

    y0 = system.default_initial_state
    t0 = 0.0
    numpy_out = system.rhs(t0, y0, **default_params)
    jax_out = _to_numpy(rhs_jax(t0, y0))

    assert numpy_out.shape == jax_out.shape, (
        f"shape mismatch for {system_cls.__name__}: "
        f"numpy={numpy_out.shape}, jax={jax_out.shape}"
    )
    np.testing.assert_allclose(
        jax_out,
        numpy_out,
        atol=_PARITY_ATOL,
        rtol=0.0,
        err_msg=f"{system_cls.__name__} canonical-IC parity failed",
    )


@pytest.mark.parametrize("system_cls, jax_factory", _PARITY_CASES)
def test_jax_rhs_matches_numpy_rhs_on_random_grid(
    system_cls,  # type: ignore[no-untyped-def]
    jax_factory,  # type: ignore[no-untyped-def]
) -> None:
    """Across a 20-point random ``(state, t)`` grid, JAX RHS == numpy RHS."""

    system = system_cls()
    default_params = {k: p.default for k, p in system.parameters.items()}
    rhs_jax = jax_factory(**default_params)

    rng = np.random.default_rng(_RANDOM_SEED)
    # Sample states from a box that spans the attractor for each system
    # without driving Chua's piecewise-linear segment to a corner case.
    # 5.0 is a safe scale for all five systems.
    states = rng.uniform(-5.0, 5.0, size=(_RANDOM_GRID_SIZE, system.state_dim))
    times = rng.uniform(0.0, _RANDOM_T_MAX, size=_RANDOM_GRID_SIZE)

    for i in range(_RANDOM_GRID_SIZE):
        y = states[i].astype(np.float64)
        t = float(times[i])
        numpy_out = system.rhs(t, y, **default_params)
        jax_out = _to_numpy(rhs_jax(t, y))
        np.testing.assert_allclose(
            jax_out,
            numpy_out,
            atol=_PARITY_ATOL,
            rtol=0.0,
            err_msg=(
                f"{system_cls.__name__} parity failed at grid point {i}: "
                f"t={t}, y={y.tolist()}"
            ),
        )


# ---------------------------------------------------------------------------
# Edge case: Chua's piecewise-linear nonlinearity. Verify the JAX and
# numpy variants agree across all three regions of the diode (inner and
# both outer slopes).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("x_probe", [-2.5, -1.0, -0.25, 0.0, 0.25, 1.0, 2.5])
def test_chua_jax_rhs_matches_numpy_across_diode_regions(x_probe: float) -> None:
    """Chua's piecewise-linear ``h(x)`` traces correctly through ``jnp.abs``.

    Probes the inner slope (|x| < 1), both diode breakpoints (|x| = 1),
    and the outer slopes (|x| > 1). The numpy and JAX implementations
    must agree exactly through ``np.abs`` -> ``jnp.abs``.
    """

    system = Chua()
    default_params = {k: p.default for k, p in system.parameters.items()}
    rhs_jax = chua_jax_rhs(**default_params)

    y = np.array([x_probe, 0.1, -0.2], dtype=np.float64)
    numpy_out = system.rhs(0.0, y, **default_params)
    jax_out = _to_numpy(rhs_jax(0.0, y))

    np.testing.assert_allclose(jax_out, numpy_out, atol=_PARITY_ATOL, rtol=0.0)


# ---------------------------------------------------------------------------
# Edge case: Duffing is non-autonomous (cos(omega * t) drive). Verify
# the JAX RHS correctly responds to the t argument rather than ignoring
# it.
# ---------------------------------------------------------------------------


def test_duffing_jax_rhs_uses_time_argument() -> None:
    """Duffing's drive ``gamma cos(omega t)`` must change RHS with ``t``."""

    system = Duffing()
    default_params = {k: p.default for k, p in system.parameters.items()}
    rhs_jax = duffing_jax_rhs(**default_params)

    y = np.array([0.5, 0.0], dtype=np.float64)
    out_t0 = _to_numpy(rhs_jax(0.0, y))
    # omega = 1 (canonical) so t = pi shifts the drive by half a period.
    out_t_pi = _to_numpy(rhs_jax(float(np.pi), y))

    # Numpy reference at the same two times.
    numpy_t0 = system.rhs(0.0, y, **default_params)
    numpy_t_pi = system.rhs(float(np.pi), y, **default_params)

    np.testing.assert_allclose(out_t0, numpy_t0, atol=_PARITY_ATOL, rtol=0.0)
    np.testing.assert_allclose(out_t_pi, numpy_t_pi, atol=_PARITY_ATOL, rtol=0.0)
    # Sanity: the drive term flips sign across half a period (cos(0) = +1,
    # cos(pi) = -1). The v-component RHS must differ by 2 * gamma.
    delta_v = float(out_t0[1] - out_t_pi[1])
    expected_delta_v = 2.0 * default_params["gamma"]
    np.testing.assert_allclose(
        delta_v, expected_delta_v, atol=_PARITY_ATOL, rtol=0.0
    )


# ---------------------------------------------------------------------------
# Smoke test: each factory's output is callable in the diffrax
# ``rhs(t, y, args)`` shape — the 3-arg call must not raise. This is
# the contract ``vmap_trajectories`` and ``JaxRK45.integrate`` rely on.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("system_cls, jax_factory", _PARITY_CASES)
def test_jax_rhs_accepts_three_arg_signature(
    system_cls,  # type: ignore[no-untyped-def]
    jax_factory,  # type: ignore[no-untyped-def]
) -> None:
    """Each ``<system>_jax_rhs`` returns a ``rhs(t, y, args=None)`` callable."""

    system = system_cls()
    default_params = {k: p.default for k, p in system.parameters.items()}
    rhs_jax = jax_factory(**default_params)
    y0 = system.default_initial_state

    # 2-arg call should work via default args.
    out_2arg = _to_numpy(rhs_jax(0.0, y0))
    # 3-arg call (diffrax form) must accept an args slot.
    out_3arg = _to_numpy(rhs_jax(0.0, y0, None))
    np.testing.assert_allclose(out_2arg, out_3arg, atol=0.0, rtol=0.0)
