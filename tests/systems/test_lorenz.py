"""Lorenz attractor tests: numerical positivity of the largest Lyapunov
exponent and exponential divergence of nearby trajectories.
"""

from __future__ import annotations

import numpy as np

from chaotic_systems.core import largest_lyapunov_two_trajectory
from chaotic_systems.systems import Lorenz


def test_nearby_trajectories_diverge_exponentially() -> None:
    """Two nearby ICs separate with the expected exponential rate.

    Starting from very nearby ICs (separation 1e-10), nearby trajectories
    on the Lorenz attractor should separate at rate
    :math:`\\lambda_1 \\approx 0.906`. We don't measure :math:`\\lambda`
    directly here (that's the job of the Benettin test); we just confirm
    the *separation grows by several orders of magnitude*.
    """
    sys = Lorenz()
    # Burn off transient so the IC lands on the attractor.
    burn = sys.simulate(
        (0.0, 50.0), n_points=2, integrator="DOP853", rtol=1e-12, atol=1e-14
    )
    y0 = burn.y[-1].copy()
    y1 = y0 + np.array([1e-10, 0.0, 0.0])

    # Two short calls; compare endpoints (no dense-output interpolation).
    traj0 = sys.simulate(
        (0.0, 15.0),
        y0=y0,
        n_points=151,
        integrator="DOP853",
        rtol=1e-12,
        atol=1e-14,
    )
    traj1 = sys.simulate(
        (0.0, 15.0),
        y0=y1,
        n_points=151,
        integrator="DOP853",
        rtol=1e-12,
        atol=1e-14,
    )
    sep = np.linalg.norm(traj0.y - traj1.y, axis=1)
    # Expect roughly log10(exp(0.906 * 15)) ~ 5.9 orders of magnitude
    # of growth before the trajectory diameter saturates. Be generous —
    # CI noise and floating-point variation cost some headroom.
    log_ratio = float(np.log10(sep[-1] / sep[0]))
    assert log_ratio > 3.0, f"separation grew only {log_ratio} orders"


def test_largest_lyapunov_lorenz_is_positive_and_close_to_known() -> None:
    """Wolf et al. (1985) report lambda_1 ~= 0.9056 for the canonical Lorenz."""
    sys = Lorenz()
    # Keep this fast — coarse parameters give us ~10% accuracy.
    lam = largest_lyapunov_two_trajectory(
        sys,
        t_transient=30.0,
        t_total=130.0,
        dt=0.5,
        delta0=1e-9,
        rng=np.random.default_rng(42),
    )
    # Just check positivity and order of magnitude. Tighter checks live
    # in the example script (more time).
    assert 0.5 < lam < 1.4
