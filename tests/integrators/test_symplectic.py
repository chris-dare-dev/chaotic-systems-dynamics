"""Symplectic integrators preserve energy on a harmonic oscillator.

We use the 1-DOF harmonic oscillator with :math:`H = p^2/2 + q^2/2`.
The analytic solution traces a circle :math:`q^2 + p^2 = E_0` in phase
space, so energy must be (very nearly) conserved by symplectic methods.

We compare against RK4 to make the point: RK4 drifts linearly in energy,
while velocity Verlet / Yoshida4 stay bounded. We additionally check
that the symplectic methods preserve phase-space area (the defining
property of a symplectic map) and the Yoshida-4 coefficients are
consistent with the canonical Yoshida (1990) values.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.integrators import RK4, leapfrog, velocity_verlet, yoshida4
from chaotic_systems.integrators._protocol import RHS
from chaotic_systems.integrators.symplectic import (
    _YOSH_COEFFS,
    _YOSH_W0,
    _YOSH_W1,
)


def _grad_T(t: float, p: np.ndarray) -> np.ndarray:
    return p.copy()


def _grad_V(t: float, q: np.ndarray) -> np.ndarray:
    return q.copy()  # V = q^2 / 2 -> grad V = q


def _energy(q: np.ndarray, p: np.ndarray) -> float:
    return float(0.5 * (np.dot(q, q) + np.dot(p, p)))


def _rk4_rhs() -> RHS:
    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        return np.array([y[1], -y[0]])

    return rhs


@pytest.mark.parametrize("integ", [velocity_verlet, leapfrog, yoshida4])
def test_symplectic_energy_bounded_over_1000_periods(integ) -> None:  # type: ignore[no-untyped-def]
    y0 = np.array([1.0, 0.0])  # q=1, p=0  =>  E=0.5
    t_end = 1000.0 * 2.0 * np.pi
    dt = 2.0 * np.pi / 200.0  # 200 steps/period
    traj = integ.integrate(
        rhs=None,  # type: ignore[arg-type]
        t_span=(0.0, t_end),
        y0=y0,
        dt=dt,
        grad_t_fn=_grad_T,
        grad_v_fn=_grad_V,
    )
    E0 = 0.5
    E = 0.5 * (traj.y[:, 0] ** 2 + traj.y[:, 1] ** 2)
    drift = float(np.max(np.abs(E - E0)))
    if integ.name == "yoshida4":
        # Yoshida4 is 4th-order: with dt=2pi/200 -> error per step ~ dt^5 ~ 1e-9;
        # over 200k steps it accumulates only as a bounded oscillation (symplectic),
        # but floating-point roundoff still gives O(sqrt(N) * eps_mach) random
        # walk. 1e-6 is a comfortable bound on practical hardware.
        assert drift < 1e-6
    else:
        # Velocity Verlet / leapfrog are 2nd-order: error per period ~ dt^3 ~ 1e-6,
        # but symplectic means the energy *oscillates* with bounded amplitude
        # rather than drifting. The amplitude is O(dt^2) here.
        assert drift < 5e-3


def test_rk4_energy_drifts_linearly() -> None:
    """RK4 is non-symplectic; the |E - E0| series should show secular growth.

    We fit ``log|E - E0|`` linearly against ``t`` and assert a positive
    slope — the canonical drift signature of a non-symplectic integrator.
    """

    y0 = np.array([1.0, 0.0])
    t_end = 1000.0 * 2.0 * np.pi
    dt = 2.0 * np.pi / 200.0
    traj = RK4.integrate(_rk4_rhs(), (0.0, t_end), y0, dt=dt)
    E = 0.5 * (traj.y[:, 0] ** 2 + traj.y[:, 1] ** 2)
    err = np.abs(E - 0.5)
    # Drop early samples where err can be exactly zero (1-ulp roundoff) and
    # confine the fit to the regime where the error has grown above the
    # floating-point floor.
    mask = err > 1e-14
    assert mask.sum() > 100, "RK4 error never rose above the FP floor"
    t = traj.t[mask]
    log_err = np.log(err[mask])
    # Linear least-squares slope of log|E - E0| vs. t.
    slope, _ = np.polyfit(t, log_err, 1)
    # A positive slope confirms RK4 is not conserving energy — error
    # is growing roughly exponentially or at least faster than O(t^0).
    # The canonical Hamiltonian-RK4 secular drift on the SHO is linear-
    # in-t in E; in log space that's still a positive slope.
    assert slope > 1e-12, f"RK4 should show growing error; got slope={slope}"

    # And Yoshida4 at the same dt beats RK4 at the final time.
    traj_y = yoshida4.integrate(
        rhs=None,  # type: ignore[arg-type]
        t_span=(0.0, t_end),
        y0=y0,
        dt=dt,
        grad_t_fn=_grad_T,
        grad_v_fn=_grad_V,
    )
    E_y = 0.5 * (traj_y.y[:, 0] ** 2 + traj_y.y[:, 1] ** 2)
    drift_y = float(np.max(np.abs(E_y - 0.5)))
    drift_rk4 = float(err[-1])
    assert drift_y < drift_rk4


def test_symplectic_requires_grad_fns() -> None:
    y0 = np.array([1.0, 0.0])
    with pytest.raises(ValueError, match="require `grad_t_fn`"):
        velocity_verlet.integrate(
            rhs=None,  # type: ignore[arg-type]
            t_span=(0.0, 1.0),
            y0=y0,
            dt=0.1,
        )


def test_symplectic_requires_dt() -> None:
    y0 = np.array([1.0, 0.0])
    with pytest.raises(ValueError, match="requires a fixed step"):
        velocity_verlet.integrate(
            rhs=None,  # type: ignore[arg-type]
            t_span=(0.0, 1.0),
            y0=y0,
            grad_t_fn=_grad_T,
            grad_v_fn=_grad_V,
        )


def test_symplectic_rejects_unexpected_kwargs() -> None:
    y0 = np.array([1.0, 0.0])
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        velocity_verlet.integrate(
            rhs=None,  # type: ignore[arg-type]
            t_span=(0.0, 1.0),
            y0=y0,
            dt=0.1,
            grad_t_fn=_grad_T,
            grad_v_fn=_grad_V,
            unknown_extra_kw="surprise",  # type: ignore[arg-type]
        )


def test_yoshida4_coefficients_match_canonical_values() -> None:
    """Verify against Yoshida (1990) eq. 4.9 — composition coefficients.

    For the 4th-order composition of three 2nd-order velocity-Verlet steps,
    the substep weights are::

        w_1 = 1 / (2 - 2^(1/3))                  ~ 1.35120719196
        w_0 = -2^(1/3) / (2 - 2^(1/3)) = 1 - 2*w_1  ~ -1.70241438392

    and the substep sequence is (w_1, w_0, w_1). These are the canonical
    coefficients; any drift here would mean the integrator no longer matches
    Yoshida's construction.
    """

    expected_w1 = 1.0 / (2.0 - 2.0 ** (1.0 / 3.0))
    expected_w0 = 1.0 - 2.0 * expected_w1
    # Same as in the source — recomputed here for the assertion.
    assert _YOSH_W1 == pytest.approx(expected_w1, rel=1e-15)
    assert _YOSH_W0 == pytest.approx(expected_w0, rel=1e-15)
    # Substep sequence is (w1, w0, w1); they sum to 1 (consistency: the
    # three substeps must cover one full time step).
    assert _YOSH_COEFFS == (expected_w1, expected_w0, expected_w1)
    assert sum(_YOSH_COEFFS) == pytest.approx(1.0, abs=1e-14)


@pytest.mark.parametrize("integ", [velocity_verlet, leapfrog, yoshida4])
def test_symplectic_preserves_phase_space_area(integ) -> None:  # type: ignore[no-untyped-def]
    """A symplectic map preserves phase-space area.

    We pick 4 initial conditions at the corners of a tiny square in
    (q, p)-space, integrate each forward, and verify the area of the
    image quadrilateral matches the initial area to machine precision
    (Yoshida4) or a small symplectic-method tolerance (Verlet).
    """

    # Tiny square around (q, p) = (0.5, 0.5), side ~ 1e-3.
    s = 1e-3
    centre = np.array([0.5, 0.5])
    initials = np.array(
        [
            centre + np.array([-s, -s]),
            centre + np.array([+s, -s]),
            centre + np.array([+s, +s]),
            centre + np.array([-s, +s]),
        ]
    )

    dt = 2.0 * np.pi / 1000.0  # very fine; we want the test to fail loud
    t_end = 4.0 * 2.0 * np.pi  # four periods

    finals = []
    for y0 in initials:
        traj = integ.integrate(
            rhs=None,  # type: ignore[arg-type]
            t_span=(0.0, t_end),
            y0=y0.copy(),
            dt=dt,
            grad_t_fn=_grad_T,
            grad_v_fn=_grad_V,
        )
        finals.append(traj.y[-1])
    finals_arr = np.asarray(finals)  # (4, 2)

    # Shoelace formula for the polygon area.
    def _polygon_area(pts: np.ndarray) -> float:
        x = pts[:, 0]
        y = pts[:, 1]
        return float(0.5 * np.abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))

    area0 = _polygon_area(initials)
    area_final = _polygon_area(finals_arr)
    rel = abs(area_final - area0) / area0
    # All three methods should preserve area; tolerance varies with order.
    bound = 1e-9 if integ.name == "yoshida4" else 1e-5
    assert rel < bound, (
        f"{integ.name} area preservation: rel={rel:.3e}, expected < {bound:.0e}"
    )
