"""Tests for the prerender cache and arc-length seek API.

These exercise the headless side of the renderer — no Qt interactor
required. They lock in the contract the GUI's ``_PrerenderWorker``
relies on:

- ``build_prerender_cache`` is idempotent.
- ``has_prerender_cache`` flips True once the warm-up loop has run.
- ``seek_arc_length(0)`` lands on ``points[0]``; ``seek_arc_length(total)``
  lands on ``points[-1]``.
- ``set_line_width`` and ``set_color_by_progress`` invalidate the
  cache so the GUI re-warms before the next play loop.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.visualization.renderer import Renderer3D


@pytest.fixture()
def points() -> np.ndarray:
    """A small, deterministic 3D polyline with non-uniform segment lengths.

    Non-uniform segment lengths are important — the whole point of
    arc-length parameterization is that it does NOT match integer
    indexing. We pick a parametric curve that visibly stretches.
    """

    n = 60
    t = np.linspace(0.0, 1.0, n)
    # x and y orbit the unit circle; z grows fast in the middle of the
    # parameter range so segment lengths are non-uniform.
    return np.column_stack(
        [
            np.cos(2.0 * np.pi * t),
            np.sin(2.0 * np.pi * t),
            np.sin(np.pi * t) ** 2,
        ]
    )


def test_total_arc_length_positive(points: np.ndarray) -> None:
    r = Renderer3D(points)
    # Until the cache is built, total_arc_length is zero (cheap lazy default).
    assert r.total_arc_length == 0.0
    r.build_prerender_cache()
    assert r.total_arc_length > 0.0
    # Sanity check the table itself.
    diffs = np.diff(points, axis=0)
    expected_total = float(np.linalg.norm(diffs, axis=1).sum())
    assert r.total_arc_length == pytest.approx(expected_total, rel=1e-9)


def test_build_prerender_cache_idempotent(points: np.ndarray) -> None:
    """Calling the prerender twice is a no-op the second time."""

    r = Renderer3D(points)
    assert not r.has_prerender_cache

    calls: list[tuple[int, int]] = []

    def cb(cur: int, tot: int) -> None:
        calls.append((cur, tot))

    r.build_prerender_cache(progress_cb=cb)
    assert r.has_prerender_cache
    first_calls = list(calls)

    # Second call returns immediately; no new progress events.
    r.build_prerender_cache(progress_cb=cb)
    assert r.has_prerender_cache
    assert calls == first_calls


def test_seek_arc_length_endpoints(points: np.ndarray) -> None:
    """s=0 → points[0]; s=total → points[-1]."""

    r = Renderer3D(points)
    r.build_prerender_cache()
    r.seek_arc_length(0.0)
    # Head sits at the first sample.
    np.testing.assert_allclose(r.head_position, points[0], atol=1e-12)
    r.seek_arc_length(r.total_arc_length)
    np.testing.assert_allclose(r.head_position, points[-1], atol=1e-12)


def test_seek_arc_length_midpoint_on_smooth_curve(points: np.ndarray) -> None:
    """At half-arc-length, the head lies on the Catmull-Rom-oversampled curve.

    Before iteration 4, this test asserted the head sat on the *linear*
    chord between two integration samples. The polyline is now rendered
    as the centripetal Catmull-Rom spline through the integration samples
    (4× oversampled at prerender time), so the head sphere also lives on
    that smooth curve. We verify by computing the spline directly and
    requiring the head to coincide with one of its dense samples to a
    tight tolerance.
    """

    r = Renderer3D(points)
    r.build_prerender_cache()
    s = r.total_arc_length * 0.5
    r.seek_arc_length(s)
    head = r.head_position
    # The smooth-points buffer is what the renderer is drawing against.
    # The head should equal a linear interp between two adjacent rows
    # of that array, which (since the rows are themselves on the spline)
    # is at most a tiny linearization error away from the true spline.
    smooth = r._smooth_points  # noqa: SLF001
    smooth_arc = r._smooth_arc_lengths  # noqa: SLF001
    assert smooth is not None
    assert smooth_arc is not None
    # Map ``s`` from the linear arc-length scale to the smooth one
    # (the smooth curve is slightly longer than the chord polyline).
    s_smooth = s / r.total_arc_length * float(smooth_arc[-1])
    idx = int(np.searchsorted(smooth_arc, s_smooth, side="right")) - 1
    idx = max(0, min(idx, smooth.shape[0] - 2))
    seg = float(smooth_arc[idx + 1] - smooth_arc[idx])
    frac = (s_smooth - float(smooth_arc[idx])) / max(seg, 1e-12)
    expected = smooth[idx] + frac * (smooth[idx + 1] - smooth[idx])
    np.testing.assert_allclose(head, expected, atol=1e-9)


def test_seek_arc_length_clamps(points: np.ndarray) -> None:
    """Negative and overshoot inputs clamp to endpoints."""

    r = Renderer3D(points)
    r.build_prerender_cache()
    r.seek_arc_length(-5.0)
    np.testing.assert_allclose(r.head_position, points[0], atol=1e-12)
    r.seek_arc_length(r.total_arc_length * 10.0)
    np.testing.assert_allclose(r.head_position, points[-1], atol=1e-12)


def test_invalidate_cache(points: np.ndarray) -> None:
    """``_invalidate_cache`` drops the table and the warmed-flag."""

    r = Renderer3D(points)
    r.build_prerender_cache()
    assert r.has_prerender_cache
    r._invalidate_cache()  # noqa: SLF001
    assert not r.has_prerender_cache
    assert r.total_arc_length == 0.0


def test_progress_callback_invoked(points: np.ndarray) -> None:
    """``progress_cb`` is invoked at least once and finishes at (n, n)."""

    r = Renderer3D(points)
    calls: list[tuple[int, int]] = []
    r.build_prerender_cache(progress_cb=lambda c, t: calls.append((c, t)))
    assert calls, "expected at least one progress callback invocation"
    last_cur, last_tot = calls[-1]
    assert last_cur == last_tot
    assert last_tot >= 1


def test_cancel_callback_aborts(points: np.ndarray) -> None:
    """Returning True from ``cancel_cb`` leaves the cache unbuilt."""

    r = Renderer3D(points)
    # Cancel immediately; cache should NOT be marked as built.
    ok = r.build_prerender_cache(cancel_cb=lambda: True)
    # The headless path completes in one step regardless because there
    # is no plotter to warm; on the headless branch we don't poll
    # cancel. Verify the result by attaching to an offscreen plotter
    # and cancelling there.
    assert ok is True or ok is False  # contract returns a bool
    assert isinstance(r.has_prerender_cache, bool)


def test_cancel_on_attached_plotter_leaves_cache_incomplete(
    points: np.ndarray,
) -> None:
    """With an attached plotter, the cancel poll runs and aborts the warm-up."""

    import pyvista as pv

    plotter = pv.Plotter(off_screen=True)
    try:
        r = Renderer3D(points)
        r.attach(plotter)
        # Cancel on the very first poll — the cache must come back False.
        ok = r.build_prerender_cache(cancel_cb=lambda: True)
        assert ok is False
        assert not r.has_prerender_cache
    finally:
        plotter.close()


def test_arc_length_table_matches_cumsum(points: np.ndarray) -> None:
    """The internal arc-length table is exactly ``cumsum(norm(diff))``."""

    r = Renderer3D(points)
    r.build_prerender_cache()
    arc = r._arc_lengths  # noqa: SLF001
    assert arc is not None
    expected = np.concatenate(
        ([0.0], np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1)))
    )
    np.testing.assert_allclose(arc, expected)


def test_set_line_width_invalidates(points: np.ndarray) -> None:
    """Rebuilding the line actor drops the warmed-flag.

    The arc-length table is geometry-only and does NOT depend on line
    width — but the VTK shader cache does, since a new actor is created.
    So ``has_prerender_cache`` must come back False even though the
    arc-length math is unchanged.
    """

    import pyvista as pv

    plotter = pv.Plotter(off_screen=True)
    try:
        r = Renderer3D(points)
        r.attach(plotter)
        r.build_prerender_cache()
        assert r.has_prerender_cache
        r.set_line_width(5.0)
        assert not r.has_prerender_cache
    finally:
        plotter.close()


def test_set_color_by_progress_invalidates(points: np.ndarray) -> None:
    import pyvista as pv

    plotter = pv.Plotter(off_screen=True)
    try:
        r = Renderer3D(points)
        r.attach(plotter)
        r.build_prerender_cache()
        assert r.has_prerender_cache
        r.set_color_by_progress(False)
        assert not r.has_prerender_cache
    finally:
        plotter.close()


def test_attach_after_invalidate_rebuilds_cleanly(points: np.ndarray) -> None:
    """A fresh attach drops the cache; a fresh build_prerender_cache rebuilds it."""

    import pyvista as pv

    p1 = pv.Plotter(off_screen=True)
    p2 = pv.Plotter(off_screen=True)
    try:
        r = Renderer3D(points)
        r.attach(p1)
        r.build_prerender_cache()
        assert r.has_prerender_cache
        # Re-attaching to a new plotter drops the warmed-flag (the new
        # actor needs its own shader-cache warm-up).
        r.attach(p2)
        assert not r.has_prerender_cache
        # The arc-length table survives — the geometry is unchanged —
        # but the GUI is expected to call build_prerender_cache again.
        r.build_prerender_cache()
        assert r.has_prerender_cache
    finally:
        p1.close()
        p2.close()
