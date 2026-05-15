"""Tests for Renderer3D animation primitives — ``step()`` and ``seek()``.

These exercise the headless side of the renderer (no Qt interactor, no
plotter actor manipulation) so they run anywhere the math layer runs.
They lock in the contract that the GUI's transport controls rely on:

- ``seek(i)`` makes the polyline show the first ``i + 1`` samples.
- ``step(n)`` makes the polyline show the first ``n`` samples (cumulative,
  not incremental).
- The head marker position tracks the last visible sample.
- ``set_color_by_progress(False)`` is callable before / after attach.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.visualization.renderer import (
    Renderer3D,
    _full_polyline_connectivity,
)


@pytest.fixture()
def points() -> np.ndarray:
    """A small, deterministic 3D polyline."""

    n = 50
    t = np.linspace(0.0, 1.0, n)
    return np.column_stack([np.cos(2.0 * np.pi * t), np.sin(2.0 * np.pi * t), t])


def test_renderer_reports_total_frames(points: np.ndarray) -> None:
    r = Renderer3D(points)
    assert r.n_frames == points.shape[0]


def test_step_advances_visible_points(points: np.ndarray) -> None:
    r = Renderer3D(points)
    # No plotter attached — step() should still update internal state without
    # raising. We verify via the post-step `current_frame` accessor.
    r.step(10)
    assert r.current_frame == 10
    r.step(25)
    assert r.current_frame == 25


def test_step_clamps_to_range(points: np.ndarray) -> None:
    r = Renderer3D(points)
    r.step(1)  # below minimum
    assert r.current_frame == 2
    r.step(10 * points.shape[0])  # above maximum
    assert r.current_frame == points.shape[0]


def test_seek_jumps_to_index(points: np.ndarray) -> None:
    r = Renderer3D(points)
    r.seek(0)
    assert r.current_frame == 2  # 0-index plus the 2-point polyline minimum
    r.seek(7)
    assert r.current_frame == 8
    r.seek(points.shape[0] - 1)
    assert r.current_frame == points.shape[0]


def test_seek_moves_head_position(points: np.ndarray) -> None:
    r = Renderer3D(points)
    r.seek(0)
    np.testing.assert_allclose(r.head_position, points[1])
    r.seek(20)
    np.testing.assert_allclose(r.head_position, points[20])
    r.seek(points.shape[0] - 1)
    np.testing.assert_allclose(r.head_position, points[-1])


def test_polyline_connectivity_truncates_with_seek(points: np.ndarray) -> None:
    """After attach + seek, the polyline's `lines` array reflects only the
    visible prefix. We exercise this through PyVista off-screen.
    """

    import pyvista as pv

    plotter = pv.Plotter(off_screen=True)
    try:
        r = Renderer3D(points)
        r.attach(plotter)
        r.seek(15)
        expected = _full_polyline_connectivity(16)
        np.testing.assert_array_equal(r._polyline.lines, expected)  # noqa: SLF001
        r.seek(points.shape[0] - 1)
        expected_full = _full_polyline_connectivity(points.shape[0])
        np.testing.assert_array_equal(r._polyline.lines, expected_full)  # noqa: SLF001
    finally:
        plotter.close()


def test_seek_interpolated_polyline_uses_floor(points: np.ndarray) -> None:
    """``seek_interpolated(5.5)`` advances the polyline to 6 samples."""

    r = Renderer3D(points)
    r.seek_interpolated(5.5)
    assert r.current_frame == 6


def test_seek_interpolated_lerps_head_position(points: np.ndarray) -> None:
    """The head sphere position is a linear interp between sample i and i+1."""

    import pyvista as pv

    plotter = pv.Plotter(off_screen=True)
    try:
        r = Renderer3D(points)
        r.attach(plotter)
        r.seek_interpolated(10.25)
        # Polyline only knows about integer prefixes.
        assert r.current_frame == 11
        expected = points[10] + 0.25 * (points[11] - points[10])
        np.testing.assert_allclose(r.head_position, points[10])  # polyline
        # Head actor uses the lerped position; we mirror that test by
        # peeking at the actor position. The actor's GetPosition returns
        # a 3-tuple. If the test runs without VTK actor backend, fall back
        # to verifying ``head_position`` matches the floor.
        actor = r._head_actor  # noqa: SLF001
        if hasattr(actor, "GetPosition"):
            pos = np.asarray(actor.GetPosition(), dtype=float)
            np.testing.assert_allclose(pos, expected, atol=1e-9)
    finally:
        plotter.close()


def test_seek_interpolated_clamps(points: np.ndarray) -> None:
    """Floats past the last sample clamp; negatives clamp to 0."""

    r = Renderer3D(points)
    r.seek_interpolated(-3.5)
    assert r.current_frame == 2  # polyline minimum
    r.seek_interpolated(1e9)
    assert r.current_frame == points.shape[0]


def test_set_color_by_progress_before_attach_is_safe(points: np.ndarray) -> None:
    """Toggling progress shading without a plotter should not raise."""

    r = Renderer3D(points)
    r.set_color_by_progress(False)
    r.set_color_by_progress(True)
    # No assertion needed beyond the absence of exceptions.


def test_set_color_by_progress_after_attach(points: np.ndarray) -> None:
    """After attach, toggling the colormap rebuilds the line actor in place."""

    import pyvista as pv

    plotter = pv.Plotter(off_screen=True)
    try:
        r = Renderer3D(points)
        r.attach(plotter)
        first_actor = r._line_actor  # noqa: SLF001
        r.set_color_by_progress(False)
        # A new actor replaces the old one, but the polyline (and the head
        # actor) survives unchanged.
        assert r._line_actor is not first_actor  # noqa: SLF001
        assert r._polyline is not None  # noqa: SLF001
        assert r._head_actor is not None  # noqa: SLF001
        r.set_color_by_progress(True)
    finally:
        plotter.close()
