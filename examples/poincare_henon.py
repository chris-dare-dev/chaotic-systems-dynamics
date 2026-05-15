"""Poincaré section of the Hénon-Heiles system through :math:`x = 0`.

We collect crossings of the trajectory through the hyperplane
:math:`x = 0` with :math:`\\dot x > 0`. The resulting set of points in
the :math:`(y, p_y)` plane reveals the well-known mixed regular /
chaotic structure of the Hénon-Heiles flow at energy
:math:`E \\approx 1/8`.

Run with::

    python examples/poincare_henon.py

The script prints the number of crossings collected and the approximate
spread on the section. To plot the section you'll want matplotlib —
that's the visualization layer's job; this script just produces the
numerical data.
"""

from __future__ import annotations

import numpy as np

from chaotic_systems.core.poincare import poincare_section
from chaotic_systems.systems import HenonHeiles


def main() -> None:
    sys = HenonHeiles()
    # State ordering: [x, y, px, py]
    # Energy ~ 1/8 = 0.125 gives mixed dynamics. We choose a few ICs
    # spanning the bounded region of phase space.
    initial_conditions = [
        np.array([0.0, -0.15, 0.49, 0.0]),
        np.array([0.0, 0.0, 0.43, 0.18]),
        np.array([0.0, 0.30, 0.0, 0.32]),
    ]
    normal = np.array([1.0, 0.0, 0.0, 0.0])  # x = 0
    for k, y0 in enumerate(initial_conditions):
        E = sys.energy(y0)
        section = poincare_section(
            sys,
            normal=normal,
            offset=0.0,
            direction=+1,
            y0=y0,
            t_span=(0.0, 1000.0),
            t_transient=20.0,
            rtol=1e-10,
            atol=1e-13,
            max_step=0.5,
        )
        n = section.t.shape[0]
        print(
            f"IC {k}: E={E:.4f}  crossings={n}  "
            f"y_range=[{section.y[:, 1].min():+.3f}, {section.y[:, 1].max():+.3f}]  "
            f"py_range=[{section.y[:, 3].min():+.3f}, {section.y[:, 3].max():+.3f}]"
        )


if __name__ == "__main__":
    main()
