"""Estimate the largest Lyapunov exponent of the Lorenz attractor.

Run with::

    python examples/lyapunov_lorenz.py

Expected output: a printed estimate close to the canonical value
:math:`\\lambda_1 \\approx 0.9056` (Wolf et al. 1985). The exact number
depends on the random perturbation direction; we fix the RNG seed for
reproducibility.
"""

from __future__ import annotations

import time

import numpy as np

from chaotic_systems.core import largest_lyapunov_two_trajectory
from chaotic_systems.systems import Lorenz


def main() -> None:
    sys = Lorenz()
    rng = np.random.default_rng(0xC0FFEE)
    start = time.perf_counter()
    lam = largest_lyapunov_two_trajectory(
        sys,
        t_transient=50.0,
        t_total=2_050.0,  # 2000 t.u. of measurement
        dt=1.0,
        delta0=1e-9,
        rng=rng,
    )
    elapsed = time.perf_counter() - start
    print(f"system:           {sys.name}")
    print(f"parameters:       {sys.default_params()}")
    print(f"largest Lyapunov: {lam:.4f}  (canonical ~0.9056)")
    print(f"elapsed:          {elapsed:.2f} s")


if __name__ == "__main__":
    main()
