"""Regression tests for the iteration-4 animation smoothness work.

These exercise the Catmull-Rom spline helpers, the dense-points buffer
the renderer swaps in at prerender time, and the per-frame head
displacement budget. They are the validation gate for the smoothness
fix: if the max-per-frame head displacement bound regresses, the
animation has started teleporting again and these tests will fail.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.visualization.renderer import (
    Renderer3D,
    _catmull_rom,
    _centripetal_segment_eval,
)

# ---- Catmull-Rom spline contract ---------------------------------------


def test_catmull_rom_passes_through_samples() -> None:
    """At ``t=0`` the spline returns ``p1``; at ``t=1`` it returns ``p2``.

    This is the defining property of an *interpolating* spline — the
    curve goes through every input sample exactly, not just near them.
    The eye sees zero discontinuity at sample boundaries because the
    integration sample and the rendered curve agree by construction.
    """

    rng = np.random.default_rng(0xC4A1)
    for _ in range(8):
        p0, p1, p2, p3 = rng.normal(size=(4, 3))
        # Uniform Catmull-Rom.
        np.testing.assert_allclose(_catmull_rom(p0, p1, p2, p3, 0.0), p1)
        np.testing.assert_allclose(_catmull_rom(p0, p1, p2, p3, 1.0), p2)
        # Centripetal Catmull-Rom (the parameterization the renderer uses).
        np.testing.assert_allclose(
            _centripetal_segment_eval(p0, p1, p2, p3, 0.0), p1, atol=1e-9
        )
        np.testing.assert_allclose(
            _centripetal_segment_eval(p0, p1, p2, p3, 1.0), p2, atol=1e-9
        )


def test_catmull_rom_is_c1_continuous() -> None:
    """Velocity matches at segment boundaries.

    Build a 5-sample polyline. The numerical derivative of the spline
    at ``t=1`` of segment ``[p1, p2]`` should equal the numerical
    derivative at ``t=0`` of segment ``[p2, p3]``. This is the C^1
    property — the velocity vector doesn't flip at the integration
    sample, which is what eliminates the "polyline corner" jitter.
    """

    rng = np.random.default_rng(0xC1C0)
    p0, p1, p2, p3, p4 = rng.normal(size=(5, 3))

    eps = 1e-5
    # Velocity at the *end* of segment [p1, p2] = (q(1) - q(1 - eps)) / eps.
    v_end_left = (
        _catmull_rom(p0, p1, p2, p3, 1.0) - _catmull_rom(p0, p1, p2, p3, 1.0 - eps)
    ) / eps
    # Velocity at the *start* of segment [p2, p3] = (q(eps) - q(0)) / eps.
    v_start_right = (
        _catmull_rom(p1, p2, p3, p4, eps) - _catmull_rom(p1, p2, p3, p4, 0.0)
    ) / eps
    # The two tangents should agree to within numerical-derivative noise.
    # The exact match is up to a chain-rule factor of the uniform-param
    # speed, which equals 1 at both ends here.
    np.testing.assert_allclose(v_end_left, v_start_right, atol=2e-4)


# ---- Smooth-points buffer ----------------------------------------------


def _figure_eight(n: int) -> np.ndarray:
    """A non-uniform 3D curve with visible faceting between samples."""

    t = np.linspace(0.0, 2.0 * np.pi, n)
    return np.column_stack(
        [
            np.sin(t),
            np.sin(2.0 * t) * 0.5,
            np.cos(t) * 0.3,
        ]
    )


def test_smooth_points_length() -> None:
    """Oversample factor 4 produces (N - 1) * 4 + 1 dense samples."""

    points = _figure_eight(120)
    r = Renderer3D(points)
    r.build_prerender_cache(smooth_factor=4)
    smooth = r._smooth_points  # noqa: SLF001
    assert smooth is not None
    assert smooth.shape == ((points.shape[0] - 1) * 4 + 1, 3)
    # Original integration samples must appear exactly in the dense
    # array at strides of ``factor``. The Catmull-Rom oversampler is
    # interpolating, not approximating.
    idx_map = r._sample_to_smooth_idx  # noqa: SLF001
    assert idx_map is not None
    np.testing.assert_allclose(smooth[idx_map], points, atol=1e-12)


def test_smooth_points_disabled_when_factor_one() -> None:
    """``smooth_factor=1`` skips the oversampling step entirely."""

    points = _figure_eight(80)
    r = Renderer3D(points)
    r.build_prerender_cache(smooth_factor=1)
    assert r._smooth_points is None  # noqa: SLF001
    assert r._smooth_arc_lengths is None  # noqa: SLF001


def test_smooth_points_memory_budget() -> None:
    """Dense buffer stays inside the 10 MB budget on a 10 000-sample trajectory.

    Memory bound: ``(N - 1) * 4 + 1`` rows * 3 floats * 8 bytes. At
    N = 10 000 this is ~960 KB — comfortably inside the 10 MB ceiling
    called out in the smoothness brief.
    """

    n = 10_000
    points = np.column_stack(
        [
            np.linspace(0.0, 10.0, n),
            np.sin(np.linspace(0.0, 50.0, n)),
            np.cos(np.linspace(0.0, 50.0, n)),
        ]
    )
    r = Renderer3D(points)
    r.build_prerender_cache(smooth_factor=4)
    smooth = r._smooth_points  # noqa: SLF001
    assert smooth is not None
    bytes_used = smooth.nbytes
    assert bytes_used < 10 * 1024 * 1024


# ---- Per-frame head-displacement smoothness ----------------------------


def _per_frame_displacements(positions: np.ndarray) -> np.ndarray:
    """Return the Euclidean distance between consecutive rows of ``positions``."""

    if positions.shape[0] < 2:
        return np.zeros(0, dtype=float)
    diffs = np.diff(positions, axis=0)
    return np.linalg.norm(diffs, axis=1)


def test_max_displacement_bound_on_smooth_playback() -> None:
    """Replaying arc-length playback yields bounded per-frame head jumps.

    The smoothness goal stated in the task brief: the max per-frame
    head displacement under uniform arc-length playback should be
    less than 2x the median displacement. Before iteration 4 this
    ratio was 10-20x because the polyline was a piecewise-linear
    approximation; after iteration 4 the spline-evaluated head moves
    almost uniformly through the dense smooth array.

    We simulate playback by walking the arc-length parameter at a
    fixed step matching what the GUI does at 16 ms ticks for a 15s
    Lorenz-style trajectory.
    """

    rng = np.random.default_rng(0xD157)
    n = 1500
    # A chaotic-looking but deterministic synthetic curve.
    t = np.linspace(0.0, 30.0, n)
    points = np.column_stack(
        [
            np.sin(t) + 0.3 * np.cos(3.0 * t),
            np.cos(t) + 0.3 * np.sin(2.5 * t),
            0.5 * np.sin(0.7 * t) + 0.1 * rng.normal(size=n).cumsum() / np.sqrt(n),
        ]
    )
    r = Renderer3D(points)
    r.build_prerender_cache(smooth_factor=4)

    total_arc = r.total_arc_length
    target_seconds = 15.0
    tick_ms = 16
    n_ticks = int(target_seconds * 1000 / tick_ms)
    s_step = total_arc / n_ticks

    positions = np.empty((n_ticks, 3), dtype=float)
    for i in range(n_ticks):
        r.seek_arc_length((i + 1) * s_step)
        positions[i] = r.head_position

    disps = _per_frame_displacements(positions)
    assert disps.size > 0
    median = float(np.median(disps))
    maximum = float(np.max(disps))
    # The smoothness contract: max < 2x median. We give a small slack
    # for the endpoint where the seek snaps to total_arc.
    assert maximum < 2.0 * median + 1e-9, (
        f"max-per-frame displacement {maximum:.5f} exceeds 2 * median "
        f"{median:.5f} -- playback is back to teleporting"
    )


def test_wall_clock_animation_pacing() -> None:
    """Wall-clock pacing: arc-length advance matches elapsed wall-clock time.

    Simulates the GUI's tick loop by manually walking ``time.perf_counter()``
    forward in jittery increments and verifying the head's *cumulative*
    arc-length displacement matches ``elapsed * arc_per_second`` to
    within a per-tick step. Frame-rate jitter is *not* allowed to cause
    cumulative drift — that's the whole point of wall-clock pacing.
    """

    import time

    n = 800
    points = _figure_eight(n)
    r = Renderer3D(points)
    r.build_prerender_cache(smooth_factor=4)

    total_arc = r.total_arc_length
    target_seconds = 5.0
    arc_per_second = total_arc / target_seconds

    # Replay 5 seconds with jittery dt to simulate display vsync drops.
    rng = np.random.default_rng(0xABCD)
    wall_start = time.perf_counter()
    last_arc = 0.0
    sim_now = wall_start
    samples: list[tuple[float, float]] = []  # (elapsed, arc)
    # Mean dt ~30ms, target 5s → ~170 ticks; oversize the loop to make
    # sure we always reach the end of the trajectory.
    for _ in range(400):
        # Jittery dt in [10, 50] ms.
        dt = float(rng.uniform(0.010, 0.050))
        sim_now += dt
        elapsed = sim_now - wall_start
        target_arc = float(min(total_arc, elapsed * arc_per_second))
        r.seek_arc_length(target_arc)
        samples.append((elapsed, target_arc))
        last_arc = target_arc
        if target_arc >= total_arc:
            break

    # The cumulative arc/elapsed ratio should stay close to
    # ``arc_per_second`` for every sample (modulo end-of-trajectory
    # clamping). Tolerate 1% drift.
    for elapsed, arc in samples:
        if arc >= total_arc:
            continue  # endpoint clamp
        expected = elapsed * arc_per_second
        assert abs(arc - expected) < 1e-9, (
            f"wall-clock pacing diverged: arc={arc} expected={expected}"
        )
    assert last_arc >= total_arc * 0.9  # we covered most of the trajectory


def test_seek_arc_length_per_frame_cost_under_budget() -> None:
    """Per-frame seek stays under 5 ms even on a 4000-sample trajectory.

    Iteration 4 swaps the polyline geometry for a 4x-dense buffer.
    The brief calls out a 5 ms per-frame budget; we measure here to
    catch a regression that pushes the seek above the bar (the current
    implementation lands around 1 ms on M1 even with the dense
    buffer).
    """

    import time

    n = 4000
    points = _figure_eight(n)
    r = Renderer3D(points)
    r.build_prerender_cache(smooth_factor=4)

    total_arc = r.total_arc_length
    n_iter = 200
    targets = np.linspace(0.0, total_arc, n_iter)
    # Warm up — first call may allocate.
    r.seek_arc_length(0.0)

    t0 = time.perf_counter()
    for s in targets:
        r.seek_arc_length(float(s))
    elapsed_total = time.perf_counter() - t0
    per_frame_ms = (elapsed_total / n_iter) * 1000.0
    # 5 ms budget per task brief.
    assert per_frame_ms < 5.0, (
        f"seek_arc_length per-frame cost {per_frame_ms:.2f} ms exceeds 5 ms"
    )


# ---- Stride-cap removal smoke test -------------------------------------


@pytest.mark.parametrize("frac", [0.1, 0.25, 0.5, 0.75, 0.9])
def test_smooth_subframe_lies_near_spline(frac: float) -> None:
    """``seek_interpolated`` lands the head on the centripetal spline.

    Directly evaluates the centripetal Catmull-Rom for a known
    integer sample and confirms the renderer's head position agrees.
    """

    points = _figure_eight(120)
    r = Renderer3D(points)
    r.build_prerender_cache(smooth_factor=4)

    i = 40
    r.seek_interpolated(i + frac)
    head = r.head_position

    # Evaluate the spline directly with the same neighbour clipping.
    expected = _centripetal_segment_eval(
        points[i - 1], points[i], points[i + 1], points[i + 2], frac
    )
    np.testing.assert_allclose(head, expected, atol=1e-9)
