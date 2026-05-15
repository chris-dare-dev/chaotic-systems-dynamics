"""Compare energy conservation of RK45 vs. a symplectic integrator.

The double pendulum's total mechanical energy :math:`E = T + V` is a
conserved quantity of the *true* dynamics. Adaptive RK45 / DOP853 stay
*close* to it but drift linearly in time; the symplectic Yoshida-4
integrator (applied to the same system through the Hamiltonian
formulation) bounds the error indefinitely.

We don't actually drive the double pendulum through Yoshida-4 here
because the double pendulum is *not* separable (kinetic energy depends
on theta1 - theta2). So we make the analogous demonstration on
:class:`HenonHeiles` — separable, 2-DOF, demonstrably chaotic — and run
the double pendulum with adaptive integrators to show its energy drift
profile.

Run with::

    python examples/double_pendulum_energy.py
"""

from __future__ import annotations

import numpy as np

from chaotic_systems.integrators import from_hamiltonian, yoshida4
from chaotic_systems.systems import DoublePendulum, HenonHeiles


def double_pendulum_energy_drift_rk45() -> None:
    sys = DoublePendulum()
    y0 = np.array([1.0, 0.5, 0.0, 0.0])
    e0 = sys.energy(y0)
    traj = sys.simulate(
        (0.0, 100.0),
        y0=y0,
        n_points=10_001,
        integrator="DOP853",
        rtol=1e-10,
        atol=1e-13,
    )
    energies = np.array([sys.energy(y) for y in traj.y])
    drift = energies - e0
    print("=== double pendulum (DOP853 adaptive) ===")
    print(f"  E0 = {e0:.10f}")
    print(f"  max |E - E0| over t=[0,100]: {float(np.max(np.abs(drift))):.3e}")
    print(f"  drift at t=100:              {float(drift[-1]):.3e}")


def henon_heiles_yoshida4() -> None:
    sys = HenonHeiles()
    y0 = sys.initial_state.copy()
    e0 = sys.energy(y0)
    H = sys.hamiltonian
    grad_T, grad_V = from_hamiltonian(yoshida4, H)
    traj = yoshida4.integrate(
        rhs=None,  # ignored
        t_span=(0.0, 1000.0),
        y0=y0,
        dt=0.05,
        grad_t_fn=grad_T,
        grad_v_fn=grad_V,
    )
    energies = np.array([sys.energy(y) for y in traj.y])
    drift = energies - e0
    print("=== Henon-Heiles (Yoshida-4 symplectic) ===")
    print(f"  E0 = {e0:.10f}")
    print(f"  max |E - E0| over t=[0,1000]: {float(np.max(np.abs(drift))):.3e}")
    print(f"  drift at t=1000:              {float(drift[-1]):.3e}")


def main() -> None:
    double_pendulum_energy_drift_rk45()
    print()
    henon_heiles_yoshida4()


if __name__ == "__main__":
    main()
