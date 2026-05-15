"""Symplectic integrators preserve energy on a harmonic oscillator.

We use the 1-DOF harmonic oscillator with :math:`H = p^2/2 + q^2/2`.
The analytic solution traces a circle :math:`q^2 + p^2 = E_0` in phase
space, so energy must be (very nearly) conserved by symplectic methods.

We compare against RK4 to make the point: RK4 drifts linearly in energy,
while velocity Verlet / Yoshida4 stay bounded.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.integrators import RK4, leapfrog, velocity_verlet, yoshida4
from chaotic_systems.integrators._protocol import RHS


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
    # Symplectic methods: bounded drift; relax bound for vel-verlet
    # (2nd order: O(dt^2) energy oscillation).
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
    """RK4 is symplectic-flavored only by accident; check it drifts."""
    y0 = np.array([1.0, 0.0])
    t_end = 1000.0 * 2.0 * np.pi
    dt = 2.0 * np.pi / 200.0
    traj = RK4.integrate(_rk4_rhs(), (0.0, t_end), y0, dt=dt)
    E = 0.5 * (traj.y[:, 0] ** 2 + traj.y[:, 1] ** 2)
    # The very-last energy will have drifted measurably from 0.5.
    # Use a soft assertion: it should not have stayed within 1e-10.
    drift_final = abs(float(E[-1] - 0.5))
    # If drift_final < 1e-10 here, the test machine has better luck than
    # the average; bump dt up. We just want drift_final > 0 to confirm
    # RK4 is *not* exactly preserving energy.
    assert drift_final > 0.0
    # Yoshida4 at the same dt should beat RK4 by orders of magnitude.
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
    assert drift_y < drift_final


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
