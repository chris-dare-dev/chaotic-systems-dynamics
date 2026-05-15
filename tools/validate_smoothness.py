"""Smoothness validator for the iteration-4 animation work.

Runs a headless Lorenz simulation, builds the prerender cache (which
installs the Catmull-Rom dense-points buffer), and replays the
arc-length playback at the GUI's actual cadence. Captures
``(wall_time, head_x, head_y, head_z)`` rows to ``/tmp/animation_trace.csv``
and reports:

- Per-frame head displacement (mean, median, max, std).
- The max/median ratio — the smoothness metric called out in the
  iteration-4 brief. Goal: < 2.0 after the fix.
- Per-frame seek cost (mean) — must stay < 5 ms.

Comparable runs with ``--linear`` disable the Catmull-Rom oversampler
(``smooth_factor=1``) so you can A/B the smoothness improvement.

Usage::

    python tools/validate_smoothness.py             # smooth (default)
    python tools/validate_smoothness.py --linear    # legacy linear
    python tools/validate_smoothness.py --csv path  # custom output
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import numpy as np

from chaotic_systems.integrators import RK45
from chaotic_systems.systems.lorenz import Lorenz
from chaotic_systems.visualization.renderer import Renderer3D


def _simulate_lorenz(n_samples: int = 2400) -> np.ndarray:
    """Run the canonical Lorenz at default parameters; return (N, 3) points."""

    system = Lorenz()
    t_end = 40.0
    traj = RK45.integrate(
        system.rhs,
        (0.0, t_end),
        np.array([1.0, 1.0, 1.0]),
        n_points=n_samples,
    )
    return np.asarray(traj.y, dtype=float)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--linear",
        action="store_true",
        help="Disable Catmull-Rom oversampling (legacy A/B baseline).",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("/tmp/animation_trace.csv"),
        help="Output CSV path for the (t, x, y, z) trace.",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=5.0,
        help="Simulated wall-clock playback duration.",
    )
    parser.add_argument(
        "--target",
        type=float,
        default=15.0,
        help="Wall-clock duration of the full trajectory at 1x.",
    )
    args = parser.parse_args()

    print("Simulating Lorenz...")
    points = _simulate_lorenz(2400)
    print(f"  n_samples: {points.shape[0]}")

    print("Building renderer + prerender cache...")
    r = Renderer3D(points)
    smooth_factor = 1 if args.linear else 4
    t0 = time.perf_counter()
    r.build_prerender_cache(smooth_factor=smooth_factor)
    print(
        f"  prerender: {(time.perf_counter() - t0) * 1000:.1f} ms, "
        f"smooth_factor={smooth_factor}"
    )

    total_arc = r.total_arc_length
    target_seconds = args.target
    arc_per_second = total_arc / target_seconds

    # Replay at 60 Hz over args.seconds of wall time.
    tick_ms = 16.0
    n_ticks = int(args.seconds * 1000.0 / tick_ms)
    print(f"Replaying {n_ticks} ticks over {args.seconds:.2f}s...")

    positions = np.empty((n_ticks, 3), dtype=float)
    wall_times = np.empty(n_ticks, dtype=float)
    seek_times = np.empty(n_ticks, dtype=float)

    wall_start = time.perf_counter()
    for i in range(n_ticks):
        elapsed = i * (tick_ms / 1000.0)
        target_arc = float(min(total_arc, elapsed * arc_per_second))
        seek_start = time.perf_counter()
        r.seek_arc_length(target_arc)
        seek_end = time.perf_counter()
        positions[i] = r.head_position
        wall_times[i] = wall_start + elapsed
        seek_times[i] = seek_end - seek_start

    # Per-frame head displacements (proxy for arc-length step size).
    diffs = np.diff(positions, axis=0)
    disps = np.linalg.norm(diffs, axis=1)

    median = float(np.median(disps))
    maximum = float(np.max(disps))
    mean = float(np.mean(disps))
    std = float(np.std(disps))
    ratio = maximum / median if median > 0 else float("inf")

    # Per-frame velocity direction-change angle. This is the metric
    # the eye actually sees as "jitter": the angle between consecutive
    # head-velocity vectors. Linear chord interpolation produces
    # sharp angle spikes at every integration-sample boundary; the
    # Catmull-Rom spline smooths them out (C^1 continuity).
    if diffs.shape[0] >= 2:
        norms = np.linalg.norm(diffs, axis=1, keepdims=True)
        unit = diffs / np.maximum(norms, 1e-12)
        dots = np.einsum("ij,ij->i", unit[:-1], unit[1:])
        dots = np.clip(dots, -1.0, 1.0)
        angles_deg = np.degrees(np.arccos(dots))
    else:
        angles_deg = np.zeros(0, dtype=float)
    angle_median = float(np.median(angles_deg)) if angles_deg.size else 0.0
    angle_max = float(np.max(angles_deg)) if angles_deg.size else 0.0
    angle_p95 = (
        float(np.percentile(angles_deg, 95)) if angles_deg.size else 0.0
    )
    angle_ratio = angle_max / angle_median if angle_median > 0 else float("inf")

    # POLYLINE BODY SMOOTHNESS. This is what the user actually sees:
    # the rendered curve between trajectory samples. With smooth_factor=4,
    # the polyline body is the Catmull-Rom spline, not the linear chord.
    # Measure by computing the velocity-angle between consecutive segments
    # of the polyline VTK draws.
    polyline_pts = (
        r._smooth_points  # noqa: SLF001
        if r._smooth_points is not None  # noqa: SLF001
        else r.points
    )
    seg = np.diff(polyline_pts, axis=0)
    seg_norms = np.linalg.norm(seg, axis=1, keepdims=True)
    seg_unit = seg / np.maximum(seg_norms, 1e-12)
    if seg_unit.shape[0] >= 2:
        seg_dots = np.einsum("ij,ij->i", seg_unit[:-1], seg_unit[1:])
        seg_dots = np.clip(seg_dots, -1.0, 1.0)
        body_angles = np.degrees(np.arccos(seg_dots))
    else:
        body_angles = np.zeros(0, dtype=float)
    body_max = float(np.max(body_angles)) if body_angles.size else 0.0
    body_p95 = (
        float(np.percentile(body_angles, 95)) if body_angles.size else 0.0
    )
    body_median = float(np.median(body_angles)) if body_angles.size else 0.0

    mean_seek_ms = float(np.mean(seek_times)) * 1000.0
    p95_seek_ms = float(np.percentile(seek_times, 95)) * 1000.0

    print()
    print(f"Smoothness ({'LINEAR' if args.linear else 'SMOOTH'}):")
    print(f"  median per-frame disp:    {median:.5f} world units")
    print(f"  mean   per-frame disp:    {mean:.5f}")
    print(f"  max    per-frame disp:    {maximum:.5f}")
    print(f"  std    per-frame disp:    {std:.5f}")
    print(f"  max/median disp ratio:    {ratio:.2f}   (goal < 2.00)")
    print(f"  median  velocity-angle:   {angle_median:.3f} deg")
    print(f"  p95     velocity-angle:   {angle_p95:.3f} deg")
    print(f"  max     velocity-angle:   {angle_max:.3f} deg")
    print(f"  max/median angle ratio:   {angle_ratio:.2f}")
    print()
    print("Polyline body (what the eye sees as the trajectory curve):")
    print(f"  median segment-angle:     {body_median:.3f} deg")
    print(f"  p95    segment-angle:     {body_p95:.3f} deg")
    print(f"  max    segment-angle:     {body_max:.3f} deg")
    print("  goal: LINEAR baseline ~10-30 deg max, SMOOTH < 5 deg max")
    print()
    print("Performance:")
    print(f"  mean seek_arc_length:     {mean_seek_ms:.3f} ms")
    print(f"  p95  seek_arc_length:     {p95_seek_ms:.3f} ms")
    print("  goal:                     < 5.000 ms")

    # Dump CSV.
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["wall_time", "x", "y", "z"])
        for t, p in zip(wall_times, positions, strict=True):
            w.writerow([f"{t:.6f}", f"{p[0]:.6f}", f"{p[1]:.6f}", f"{p[2]:.6f}"])
    print(f"  trace written to {args.csv}")

    # Verdict.
    print()
    if ratio < 2.0 and p95_seek_ms < 5.0:
        print("PASS - smoothness goal met, performance within budget.")
    elif ratio < 2.0:
        print(f"PARTIAL - smoothness met but p95 seek {p95_seek_ms:.2f} ms over 5 ms.")
    elif p95_seek_ms < 5.0:
        print(f"PARTIAL - performance met but ratio {ratio:.2f} over 2.0.")
    else:
        print("FAIL - both smoothness and performance goals missed.")
    # Velocity-angle hint for A/B comparisons.
    if angle_max > 30.0:
        print(f"NOTE: max velocity angle {angle_max:.1f} deg is in 'visible "
              "corner' territory (typical LINEAR baseline). Rerun without "
              "--linear to see the smooth path.")


if __name__ == "__main__":
    main()
