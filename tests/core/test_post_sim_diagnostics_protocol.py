"""Tests for the PostSimDiagnosticProvider Protocol (CSC-033 / T3).

The Protocol contract:

- ``PostSimDiagnosticProvider`` is ``runtime_checkable`` —
  ``isinstance(system, PostSimDiagnosticProvider)`` works on any
  class that has a ``post_sim_diagnostics`` method with the right
  signature.
- Concrete providers shipped: ``Kuramoto``, ``HenonHeiles``,
  ``DoublePendulum``. Non-providers (Lorenz, Rossler, Chua, …) are
  expected to return False from the isinstance check.
- Each provider's ``post_sim_diagnostics(trajectory)`` returns a
  dict of pre-formatted display strings.
- ``format_post_sim_diagnostics`` joins the dict into a single
  newline-separated display block matching the indentation of the
  spectrum block in ``_format_lyapunov_spectrum``.

Numerical observables pinned here:

- Kuramoto at K = 1.5 (canonical default; K_c = 1) shows ``|r|``
  significantly above the K = 0 incoherent floor when run for long
  enough to lock — we use the analytic K = 0 case to verify the
  formatting path is exact, and Kuramoto with a short hand-crafted
  trajectory to verify the observable values.
- HenonHeiles ``post_sim_diagnostics`` against a stationary
  trajectory must report ``|ΔE/E₀| = 0`` to machine precision (E
  matches at first and last frame).
- DoublePendulum ``post_sim_diagnostics`` reads ``trajectory.params``
  when present (the system needs masses/lengths for energy) and
  falls back to defaults when absent.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.core import (
    PostSimDiagnosticProvider,
    Trajectory,
    format_post_sim_diagnostics,
)
from chaotic_systems.systems.chua import Chua
from chaotic_systems.systems.double_pendulum import DoublePendulum
from chaotic_systems.systems.duffing import Duffing
from chaotic_systems.systems.henon_heiles import HenonHeiles
from chaotic_systems.systems.kuramoto import Kuramoto
from chaotic_systems.systems.lorenz import Lorenz
from chaotic_systems.systems.rossler import Rossler

# ---------------------------------------------------------------------------
# Protocol isinstance contract.
# ---------------------------------------------------------------------------


def test_kuramoto_implements_protocol() -> None:
    assert isinstance(Kuramoto(), PostSimDiagnosticProvider)


def test_henon_heiles_implements_protocol() -> None:
    assert isinstance(HenonHeiles(), PostSimDiagnosticProvider)


def test_double_pendulum_implements_protocol() -> None:
    assert isinstance(DoublePendulum(), PostSimDiagnosticProvider)


@pytest.mark.parametrize("system_cls", [Lorenz, Rossler, Chua, Duffing])
def test_non_providers_do_not_match_protocol(system_cls) -> None:  # type: ignore[no-untyped-def]
    """Systems without observable hooks must not pretend to implement it."""
    assert not isinstance(system_cls(), PostSimDiagnosticProvider)


# ---------------------------------------------------------------------------
# format_post_sim_diagnostics shape.
# ---------------------------------------------------------------------------


def test_format_empty_dict_returns_empty_string() -> None:
    assert format_post_sim_diagnostics({}) == ""


def test_format_dict_emits_two_space_indented_kv_lines() -> None:
    block = format_post_sim_diagnostics({"|r|": "0.87", "ψ": "+1.04"})
    assert block == "  |r| = 0.87\n  ψ = +1.04"


def test_format_preserves_insertion_order() -> None:
    block = format_post_sim_diagnostics(
        {"E": "+1.25e-01", "|ΔE/E₀|": "3.4e-08"}
    )
    lines = block.splitlines()
    assert lines[0].endswith("E = +1.25e-01")
    assert lines[1].endswith("|ΔE/E₀| = 3.4e-08")


# ---------------------------------------------------------------------------
# Kuramoto observable.
# ---------------------------------------------------------------------------


def _toy_trajectory(y: np.ndarray, *, system_name: str = "Kuramoto") -> Trajectory:
    """Build a minimal :class:`Trajectory` with the given final state."""
    return Trajectory(
        t=np.linspace(0.0, 1.0, y.shape[0]),
        y=y,
        system=system_name,
        params={},
        integrator="test",
    )


def test_kuramoto_post_sim_with_fully_aligned_phases_reports_unit_r() -> None:
    """All N phases at the same angle -> |r| = 1."""
    system = Kuramoto(n=10)
    # Two frames; final frame is fully aligned at theta = 0.
    y = np.zeros((2, 10), dtype=np.float64)
    obs = system.post_sim_diagnostics(_toy_trajectory(y))
    assert "|r|" in obs
    assert "ψ" in obs
    assert float(obs["|r|"]) == pytest.approx(1.0)
    # When all phases are 0, the mean phase psi is 0.
    assert float(obs["ψ"]) == pytest.approx(0.0)


def test_kuramoto_post_sim_with_evenly_spaced_phases_reports_zero_r() -> None:
    """Phases uniformly spread on the circle -> |r| = 0."""
    system = Kuramoto(n=12)
    # Final frame: phases spaced evenly around the unit circle.
    final = np.linspace(0.0, 2.0 * np.pi, 12, endpoint=False)
    y = np.vstack([np.zeros(12), final])
    obs = system.post_sim_diagnostics(_toy_trajectory(y))
    assert float(obs["|r|"]) == pytest.approx(0.0, abs=1e-12)


def test_kuramoto_post_sim_empty_trajectory_returns_empty_dict() -> None:
    system = Kuramoto(n=4)
    empty = Trajectory(
        t=np.array([], dtype=np.float64),
        y=np.zeros((0, 4), dtype=np.float64),
        system="Kuramoto",
        params={},
        integrator="test",
    )
    assert system.post_sim_diagnostics(empty) == {}


# ---------------------------------------------------------------------------
# HenonHeiles observable.
# ---------------------------------------------------------------------------


def test_henon_heiles_post_sim_constant_trajectory_drift_zero() -> None:
    """If first == last frame, |ΔE/E₀| must be exactly 0."""
    system = HenonHeiles()
    y = np.tile(np.array([0.1, 0.2, 0.3, 0.4]), (5, 1))
    obs = system.post_sim_diagnostics(_toy_trajectory(y, system_name="HenonHeiles"))
    assert "E" in obs
    assert "|ΔE/E₀|" in obs
    assert float(obs["|ΔE/E₀|"]) == 0.0
    # E value at this state is computable directly.
    expected_e = system.energy(np.array([0.1, 0.2, 0.3, 0.4]))
    assert float(obs["E"]) == pytest.approx(expected_e, rel=1e-3)


def test_henon_heiles_post_sim_drift_nonzero_when_states_differ() -> None:
    system = HenonHeiles()
    y = np.array(
        [
            [0.0, 0.1, 0.45, 0.0],
            [0.05, 0.15, 0.30, 0.20],
        ]
    )
    obs = system.post_sim_diagnostics(_toy_trajectory(y, system_name="HenonHeiles"))
    # Drift parsed back from scientific notation; sanity-check sign and bound.
    drift = float(obs["|ΔE/E₀|"])
    assert drift > 0.0
    assert drift < 10.0  # arbitrary upper bound; just verify it's a real ratio


def test_henon_heiles_post_sim_empty_trajectory_returns_empty() -> None:
    system = HenonHeiles()
    empty = Trajectory(
        t=np.array([], dtype=np.float64),
        y=np.zeros((0, 4), dtype=np.float64),
        system="HenonHeiles",
        params={},
        integrator="test",
    )
    assert system.post_sim_diagnostics(empty) == {}


# ---------------------------------------------------------------------------
# DoublePendulum observable.
# ---------------------------------------------------------------------------


def test_double_pendulum_post_sim_uses_trajectory_params() -> None:
    """The provider reads trajectory.params for masses/lengths."""
    system = DoublePendulum()
    state = np.array([1.0, 0.5, 0.2, -0.1])
    y = np.tile(state, (3, 1))
    # Supply non-default params via trajectory.params so the provider
    # picks them up rather than falling back to system defaults.
    params = {"m1": 1.2, "m2": 0.8, "l1": 1.5, "l2": 0.9, "g": 9.81}
    traj = Trajectory(
        t=np.linspace(0.0, 1.0, 3),
        y=y,
        system="DoublePendulum",
        params=params,
        integrator="test",
    )
    obs = system.post_sim_diagnostics(traj)
    assert "E" in obs
    # Drift is 0 because the trajectory is stationary.
    assert "|ΔE/E₀|" in obs
    assert float(obs["|ΔE/E₀|"]) == 0.0
    # E matches energy(state, params) exactly.
    expected = system.energy(state, params)
    assert float(obs["E"]) == pytest.approx(expected, rel=1e-3)


def test_double_pendulum_post_sim_falls_back_on_missing_params() -> None:
    """If trajectory.params is missing, the provider uses defaults."""
    system = DoublePendulum()
    state = np.array([1.0, 0.5, 0.2, -0.1])
    y = np.tile(state, (2, 1))
    traj = Trajectory(
        t=np.array([0.0, 1.0]),
        y=y,
        system="DoublePendulum",
        params={},  # empty -> merged_params returns defaults
        integrator="test",
    )
    obs = system.post_sim_diagnostics(traj)
    assert "E" in obs
    expected = system.energy(state)  # default params
    assert float(obs["E"]) == pytest.approx(expected, rel=1e-3)


def test_double_pendulum_post_sim_empty_trajectory_returns_empty() -> None:
    system = DoublePendulum()
    empty = Trajectory(
        t=np.array([], dtype=np.float64),
        y=np.zeros((0, 4), dtype=np.float64),
        system="DoublePendulum",
        params={},
        integrator="test",
    )
    assert system.post_sim_diagnostics(empty) == {}
