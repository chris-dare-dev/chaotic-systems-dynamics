"""Double pendulum tests — exercise the Lagrangian -> ODE pipeline.

We do two checks:

1. The symbolic Lagrangian, when restricted to the *single* pendulum
   (massless lower link), reproduces the analytic single-pendulum ODE.
2. With the full two-pendulum parameters, energy is approximately
   conserved over a short integration window using a high-accuracy
   adaptive integrator (DOP853 with tight tolerances).
"""

from __future__ import annotations

import numpy as np

from chaotic_systems.systems import DoublePendulum


def test_single_pendulum_limit_matches_analytic_ode() -> None:
    """Set m2=0, l2=tiny — the upper bob then obeys
    theta1_ddot = -(g/l1) sin(theta1).
    """
    sys = DoublePendulum()
    params = {"m1": 1.0, "m2": 1e-9, "l1": 1.0, "l2": 1e-9, "g": 9.81}
    for theta in [0.1, -0.5, 1.0, 1.5]:
        y = np.array([theta, 0.0, 0.0, 0.0])
        dy = sys.rhs(0.0, y, **params)
        # dy = [theta1_dot, theta2_dot, theta1_ddot, theta2_ddot]
        expected_theta1_ddot = -(params["g"] / params["l1"]) * np.sin(theta)
        assert abs(dy[2] - expected_theta1_ddot) < 1e-5


def test_energy_conservation_short_horizon() -> None:
    """The DOP853 integrator preserves energy to ~1e-8 over 10 time units."""
    sys = DoublePendulum()
    y0 = np.array([1.0, 0.5, 0.0, 0.0])
    e0 = sys.energy(y0)
    traj = sys.simulate(
        (0.0, 10.0),
        y0=y0,
        n_points=201,
        integrator="DOP853",
        rtol=1e-11,
        atol=1e-14,
    )
    energies = np.array([sys.energy(y) for y in traj.y])
    drift = float(np.max(np.abs(energies - e0)))
    assert drift < 1e-7


def test_lagrangian_latex_is_nonempty() -> None:
    sys = DoublePendulum()
    assert sys.lagrangian_latex is not None
    assert "theta" in sys.lagrangian_latex or r"\theta" in sys.lagrangian_latex
