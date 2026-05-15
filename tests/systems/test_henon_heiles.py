"""Hénon-Heiles tests: symplectic integration preserves energy."""

from __future__ import annotations

import numpy as np

from chaotic_systems.core.poincare import poincare_section
from chaotic_systems.integrators import from_hamiltonian, yoshida4
from chaotic_systems.systems import HenonHeiles


def test_yoshida4_preserves_henon_heiles_energy() -> None:
    sys = HenonHeiles()
    # Energy ~ 0.125 (mixed regime).
    y0 = np.array([0.0, -0.15, 0.49, 0.0])
    E0 = sys.energy(y0)
    H = sys.hamiltonian
    grad_T, grad_V = from_hamiltonian(yoshida4, H)
    traj = yoshida4.integrate(
        rhs=None,  # type: ignore[arg-type]
        t_span=(0.0, 200.0),
        y0=y0,
        dt=0.05,
        grad_t_fn=grad_T,
        grad_v_fn=grad_V,
    )
    energies = np.array([sys.energy(y) for y in traj.y])
    drift = float(np.max(np.abs(energies - E0)))
    # Yoshida4 should preserve energy to ~ 1e-7 at this step size.
    assert drift < 1e-6


def test_poincare_section_returns_finite_points() -> None:
    """Section x = 0, p_x > 0 should pick up many crossings in 200 t.u."""
    sys = HenonHeiles()
    # state ordering: [x, y, px, py]; normal = e_x; direction = +1 picks px>0.
    normal = np.array([1.0, 0.0, 0.0, 0.0])
    pts = poincare_section(
        sys,
        normal=normal,
        offset=0.0,
        direction=+1,
        y0=np.array([0.0, -0.15, 0.49, 0.0]),
        t_span=(0.0, 200.0),
        t_transient=10.0,
        max_step=0.5,
    )
    assert pts.y.shape[1] == 4
    assert pts.y.shape[0] > 5
    # Points must lie on the hyperplane x = 0 to numerical precision.
    np.testing.assert_allclose(pts.y[:, 0], 0.0, atol=1e-8)
    # Energy of section points is approximately E0 (energy is conserved).
    E0 = sys.energy(np.array([0.0, -0.15, 0.49, 0.0]))
    section_E = np.array([sys.energy(p) for p in pts.y])
    assert float(np.max(np.abs(section_E - E0))) < 1e-6
