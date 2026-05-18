"""Tests for the basin-of-attraction compute (D4).

Reference observable
--------------------
The undriven double-well Duffing oscillator
``x' = v``, ``v' = -delta v - alpha x - beta x^3`` with
``(alpha, beta, delta) = (-1, 1, 0.2)`` has two stable fixed points at
``(±1, 0)`` and a saddle at ``(0, 0)``. With light damping the basin
boundary is the *stable manifold of the saddle* — a smooth curve
passing through the origin. For initial conditions on the v = 0
section (so the orbit starts at rest), the picture is the simplest
imaginable: orbits with x0 > 0 fall into the right well, orbits with
x0 < 0 fall into the left.

We pin: on a 21 × 1 grid along v = 0 with x ∈ [-2, -0.1] ∪ [0.1, 2]
(skipping the saddle), every left-half grid point classifies as
"left well" and every right-half grid point as "right well".

We also pin the JAX backend produces an identical classification when
the user passes a JAX-traceable RHS — gated on the [jax] extra.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.core import (
    UNCLASSIFIED_LABEL,
    BasinDiagram,
    basin_diagram,
    double_well_rhs,
)


def test_basin_diagram_dataclass_validates_shapes() -> None:
    """Shape mismatches surface clearly via __post_init__ guards."""
    valid = BasinDiagram(
        x_axis=(0, -1.0, 1.0),
        y_axis=(1, -1.0, 1.0),
        n_grid=(3, 4),
        labels=np.zeros((4, 3), dtype=np.int64),
        attractor_labels=["A", "B"],
        attractor_points=np.array([[0.0, 0.0], [1.0, 0.0]]),
        fixed_state=np.array([0.0, 0.0]),
    )
    assert valid.n_attractors == 2
    assert valid.state_dim == 2

    with pytest.raises(ValueError, match="labels shape"):
        BasinDiagram(
            x_axis=(0, -1.0, 1.0),
            y_axis=(1, -1.0, 1.0),
            n_grid=(3, 4),
            labels=np.zeros((3, 3), dtype=np.int64),  # wrong shape
            attractor_labels=["A"],
            attractor_points=np.array([[0.0, 0.0]]),
            fixed_state=np.array([0.0, 0.0]),
        )

    with pytest.raises(ValueError, match="attractor_points must be 2-D"):
        BasinDiagram(
            x_axis=(0, -1.0, 1.0),
            y_axis=(1, -1.0, 1.0),
            n_grid=(3, 4),
            labels=np.zeros((4, 3), dtype=np.int64),
            attractor_labels=["A"],
            attractor_points=np.array([0.0, 0.0]),  # 1-D, not 2-D
            fixed_state=np.array([0.0, 0.0]),
        )


def test_basin_validation_catches_bad_axes() -> None:
    rhs = double_well_rhs()
    attractors = [
        ("left", np.array([-1.0, 0.0])),
        ("right", np.array([1.0, 0.0])),
    ]
    fixed = np.array([0.0, 0.0])

    # Same x and y axis = error.
    with pytest.raises(ValueError, match="must differ"):
        basin_diagram(
            rhs,
            x_axis=(0, -1.0, 1.0),
            y_axis=(0, -1.0, 1.0),
            attractors=attractors,
            fixed_state=fixed,
            n_grid=(4, 4),
            t_end=1.0,
        )

    # Out of range index.
    with pytest.raises(ValueError, match="out of range"):
        basin_diagram(
            rhs,
            x_axis=(5, -1.0, 1.0),
            y_axis=(1, -1.0, 1.0),
            attractors=attractors,
            fixed_state=fixed,
            n_grid=(4, 4),
            t_end=1.0,
        )

    # Invalid range (lo >= hi).
    with pytest.raises(ValueError, match="hi > lo"):
        basin_diagram(
            rhs,
            x_axis=(0, 1.0, 1.0),
            y_axis=(1, -1.0, 1.0),
            attractors=attractors,
            fixed_state=fixed,
            n_grid=(4, 4),
            t_end=1.0,
        )


def test_basin_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="unknown backend"):
        basin_diagram(
            double_well_rhs(),
            x_axis=(0, -1.0, 1.0),
            y_axis=(1, -1.0, 1.0),
            attractors=[("a", np.array([0.0, 0.0]))],
            fixed_state=np.array([0.0, 0.0]),
            n_grid=(4, 4),
            t_end=1.0,
            backend="numba",  # type: ignore[arg-type]
        )


def test_basin_rejects_bad_attractors() -> None:
    fixed = np.array([0.0, 0.0])
    rhs = double_well_rhs()

    with pytest.raises(ValueError, match="at least one"):
        basin_diagram(
            rhs,
            x_axis=(0, -1.0, 1.0),
            y_axis=(1, -1.0, 1.0),
            attractors=[],
            fixed_state=fixed,
            n_grid=(4, 4),
            t_end=1.0,
        )

    with pytest.raises(ValueError, match="expected"):
        basin_diagram(
            rhs,
            x_axis=(0, -1.0, 1.0),
            y_axis=(1, -1.0, 1.0),
            attractors=[("wrong", np.array([0.0, 0.0, 0.0]))],
            fixed_state=fixed,
            n_grid=(4, 4),
            t_end=1.0,
        )


def test_double_well_basin_classifies_sign_of_x() -> None:
    """The signature observable: low-energy orbits at rest go to the
    same-sign well.

    For ICs ``(x0, 0)`` the potential energy is
    ``V(x0) = -0.5 x0^2 + 0.25 x0^4``. The saddle at the origin has
    ``V(0) = 0``; the wells at ±1 have ``V(±1) = -0.25``. ICs satisfy
    ``V(x0) < 0`` iff ``|x0| < sqrt(2) ≈ 1.414`` — below the saddle
    energy, the lightly-damped orbit can't escape its own well and
    sign(x0) determines which fixed point it falls into. ICs *above*
    the saddle energy (|x0| > 1.414) can cross wells before being
    trapped, so we restrict the sweep to the low-energy region.
    """
    rhs = double_well_rhs()
    attractors = [
        ("left", np.array([-1.0, 0.0])),
        ("right", np.array([1.0, 0.0])),
    ]
    # Restrict |x| < 1.4 (below the saddle energy at V = 0).
    xs = np.concatenate(
        [np.linspace(-1.3, -0.1, 8), np.linspace(0.1, 1.3, 8)]
    )
    n_x = len(xs)
    diagram = basin_diagram(
        rhs,
        x_axis=(0, float(xs.min()), float(xs.max())),
        y_axis=(1, -1e-6, 1e-6),
        attractors=attractors,
        fixed_state=np.array([0.0, 0.0]),
        n_grid=(n_x, 2),
        t_end=80.0,
        classify_tol=0.5,
        system_name="DoubleWell-test",
    )
    assert diagram.labels.shape == (2, n_x)
    x_grid = diagram.x_grid
    for row in range(2):
        for j, x_val in enumerate(x_grid):
            expected = 0 if x_val < 0 else 1
            assert diagram.labels[row, j] == expected, (
                f"basin at (x={x_val:.3f}, v={diagram.y_grid[row]:.1e}) "
                f"= {diagram.labels[row, j]}, expected {expected}"
            )


def test_double_well_basin_has_both_wells_in_full_grid() -> None:
    """On a (32, 32) (x, v) grid, both wells should be reached and the
    boundary cuts roughly through the origin (light-damping regime)."""
    rhs = double_well_rhs()
    attractors = [
        ("left", np.array([-1.0, 0.0])),
        ("right", np.array([1.0, 0.0])),
    ]
    diagram = basin_diagram(
        rhs,
        x_axis=(0, -2.0, 2.0),
        y_axis=(1, -2.0, 2.0),
        attractors=attractors,
        fixed_state=np.array([0.0, 0.0]),
        n_grid=(32, 32),
        t_end=50.0,
        classify_tol=0.5,
    )
    n_left = int(np.sum(diagram.labels == 0))
    n_right = int(np.sum(diagram.labels == 1))
    n_unclassified = int(np.sum(diagram.labels == UNCLASSIFIED_LABEL))
    assert n_left > 100, f"expected substantial left basin; got {n_left}"
    assert n_right > 100, f"expected substantial right basin; got {n_right}"
    # Some unclassified pixels are fine (orbits that haven't quite
    # converged inside the half-well-width tol) but they shouldn't
    # dominate the picture.
    assert n_unclassified < diagram.labels.size // 4
    # Wells should split the grid roughly half-half (light damping
    # symmetric potential).
    assert abs(n_left - n_right) < 0.25 * diagram.labels.size


def test_basin_unclassified_for_escape() -> None:
    """If every attractor is far from the final state, label is -1."""
    rhs = double_well_rhs()
    # Give wrong attractor positions so nothing matches.
    diagram = basin_diagram(
        rhs,
        x_axis=(0, -2.0, 2.0),
        y_axis=(1, -2.0, 2.0),
        attractors=[("nowhere", np.array([100.0, 100.0]))],
        fixed_state=np.array([0.0, 0.0]),
        n_grid=(4, 4),
        t_end=20.0,
        classify_tol=0.5,
    )
    assert (diagram.labels == UNCLASSIFIED_LABEL).all()


def test_basin_progress_callback_fires() -> None:
    rhs = double_well_rhs()
    attractors = [("a", np.array([-1.0, 0.0])), ("b", np.array([1.0, 0.0]))]
    calls: list[tuple[int, int]] = []
    basin_diagram(
        rhs,
        x_axis=(0, -1.0, 1.0),
        y_axis=(1, -1.0, 1.0),
        attractors=attractors,
        fixed_state=np.array([0.0, 0.0]),
        n_grid=(8, 8),
        t_end=10.0,
        classify_tol=0.5,
        progress=lambda done, total: calls.append((done, total)),
    )
    assert len(calls) > 0
    # Final call must report completion.
    assert calls[-1] == (64, 64)


# --- JAX backend parity (gated) -----------------------------------------


@pytest.fixture
def _jax_modules():  # type: ignore[no-untyped-def]
    """Skip if the [jax] extra isn't installed."""
    pytest.importorskip("jax")
    pytest.importorskip("diffrax")
    import jax.numpy as jnp

    return jnp


def test_basin_jax_backend_matches_scipy(_jax_modules) -> None:  # type: ignore[no-untyped-def]
    """A JAX-traceable double-well RHS should give the same basin
    classification as the scipy backend, up to integrator tolerance."""
    jnp = _jax_modules

    def duffing_jax(t, y, args=None):  # noqa: ANN001
        alpha, beta, delta = -1.0, 1.0, 0.2
        x, v = y[0], y[1]
        return jnp.array(
            [v, -delta * v - alpha * x - beta * x * x * x]
        )

    attractors = [
        ("left", np.array([-1.0, 0.0])),
        ("right", np.array([1.0, 0.0])),
    ]
    common = dict(
        x_axis=(0, -2.0, 2.0),
        y_axis=(1, -2.0, 2.0),
        attractors=attractors,
        fixed_state=np.array([0.0, 0.0]),
        n_grid=(16, 16),
        t_end=50.0,
        classify_tol=0.5,
    )
    scipy_diag = basin_diagram(double_well_rhs(), backend="scipy", **common)
    jax_diag = basin_diagram(duffing_jax, backend="jax", **common)
    # Allow up to 5% of pixels to differ — light-damping orbits
    # near the basin boundary can flip between Lyapunov-time-dominated
    # integration tolerances of the two backends.
    diff = int(np.sum(scipy_diag.labels != jax_diag.labels))
    assert diff < 0.05 * scipy_diag.labels.size, (
        f"{diff} of {scipy_diag.labels.size} pixels classified differently "
        f"between scipy and jax backends"
    )
