# Animation smoothness — iteration 4 investigation

Living document for the iteration-4 smoothness work landed on 2026-05-15
(commits `155b831`, `22d9896`, and the follow-ups). Read this if you
need to understand *why* the renderer maintains a Catmull-Rom dense
points buffer, why the GUI tick loop is wall-clock paced, and what to
measure if the user reports playback "looks buggy" again.

## What the user reported

> "the animation still feels very buggy and not continuous enough...
> make it so that the particle does not jump around and appears to flow
> continuously even if the particle is moving extremely fast."

Three prior iterations had landed:
- `f434eb7` (60 Hz timer + sub-frame head interpolation).
- `449759b` (cleared `verts`, fractional tail point).
- `190f45f` (stride cap 2, 60 samples per simulated second).
- `ceb6e6d` (prerender pipeline + arc-length playback, stable head).

The remaining complaints came down to three root causes the prior
passes did not address.

## Root causes (iteration 4)

### 1. Linear interpolation gives C^0 continuity, not C^1

`seek_arc_length(s)` finds the segment `[points[i], points[i+1]]`
containing arc-length `s` and does a *linear* interpolation
`head = p_i + frac * (p_{i+1} - p_i)`. The polyline tail slot in
`seek_interpolated` does the same. That gives C^0 continuity (no
position jump) but **not** C^1 — the velocity vector flips direction
at every integration-sample boundary. The eye perceives this as
micro-jitter even when there is no spatial discontinuity.

**Fix:** evaluate head and polyline-tail position via centripetal
Catmull-Rom spline. `_catmull_rom(p0, p1, p2, p3, t)` is the uniform
form; `_centripetal_segment_eval(p0, p1, p2, p3, frac)` reparameterises
by `||P_{i+1} - P_i||^0.5` to avoid the overshoot/self-loop artifacts
of plain uniform Catmull-Rom (Yuksel et al. 2011, "On the
Parameterization of Catmull-Rom Curves").

C^1 is verified numerically in
`tests/visualization/test_smoothness.py::test_catmull_rom_is_c1_continuous`.

### 2. The polyline body is a piecewise-linear approximation

Even with spline-interpolated head/tail, the *rendered polyline body*
was straight line segments between trajectory samples. In fast Lorenz
regions adjacent samples are visibly far apart in screen space — the
eye reads the polygonal-curve approximation as faceted.

**Fix:** at prerender time, oversample the trajectory `factor`
times (default 4) via Catmull-Rom and swap the VTK PolyData to render
against the dense `_smooth_points` buffer.

For a 2400-sample Lorenz this is a 9 597 × 3 float64 array — 225 KB
in memory, well inside the 10 MB budget. The original integration
samples stay in `self.points` for parameter-display / t-value lookup
purposes; `_sample_to_smooth_idx` maps integration sample `i` to the
dense index `i * factor` so the GUI's scrubber and time-label keep
working.

Measurement on a 2400-sample Lorenz, 5 s playback, 312 ticks:

|                        | LINEAR  | SMOOTH  | improvement |
| ---------------------- | ------- | ------- | ----------- |
| Median segment-angle   |  8.16°  |  2.03°  |  4.0x       |
| p95 segment-angle      | 15.75°  |  3.94°  |  4.0x       |
| Max segment-angle      | 20.80°  |  5.59°  |  3.7x       |

The polyline body's max corner angle drops from 20.8° (visibly
faceted) to 5.6° (reads as a smooth curve). Run
`python tools/validate_smoothness.py` (smooth) vs
`python tools/validate_smoothness.py --linear` (legacy baseline) to
reproduce.

### 3. QTimer at 16 ms is not vsync-locked

The QTimer fires "approximately" every 16 ms but isn't synchronised
with the display's vsync (60 Hz on most Retina displays — 16.667 ms).
The original tick loop accumulated per-tick stride increments, so a
missed timer tick stretched playback longer than
`target_playback_seconds` and visibly jittered.

**Fix:** wall-clock animation pacing. On `_play()` we record
`_play_wall_start = time.perf_counter()` and `_play_arc_start =
_anim_arc_position`. Each tick computes
`target_arc = _play_arc_start + (now - wall_start) * arc_per_second * speed`.
A late or dropped frame causes the next render to land at the
correct wall-clock position — visually smoother under jitter and
locks 1× playback to the exact `target_playback_seconds` duration.

Switching speed mid-playback rebases the anchors so the head doesn't
jump (see `_on_speed_changed`).

## Files touched

- `src/chaotic_systems/visualization/renderer.py`
  - Added `_catmull_rom`, `_centripetal_segment_eval`,
    `_spline_neighbour_indices` helpers.
  - Added `_smooth_points`, `_smooth_arc_lengths`,
    `_sample_to_smooth_idx`, `_smooth_stride` instance state.
  - Added `_allocate_render_buffers`, `_render_points`,
    `_build_smooth_points`, `_install_smooth_geometry`,
    `_smooth_subframe`, `_seek_arc_length_smooth`.
  - `build_prerender_cache` now takes `smooth_factor`
    (default `SMOOTH_OVERSAMPLE_FACTOR = 4`).
  - `seek_interpolated` and `seek_arc_length` consult the smooth path
    when the dense array is in place.
- `src/chaotic_systems/gui/main_window.py`
  - `_play()`, `_on_speed_changed`, `_on_anim_tick` rewritten to use
    wall-clock pacing.
  - Added `_play_wall_start`, `_play_arc_start`, `_play_position_start`,
    `_anim_trace`, and `_record_trace`.
- `tests/visualization/test_smoothness.py` — 13 new tests.
- `tests/visualization/test_prerender.py` — updated midpoint-on-segment
  test to expect smooth-curve geometry.
- `tools/validate_smoothness.py` — A/B validator with both
  per-frame-disp and polyline-body smoothness metrics.
- `tools/capture_polyline_screenshots.py` — visual regression aid.

## How to validate after future renderer changes

Run the smoothness regression tests:

```
pytest tests/visualization/test_smoothness.py -v
```

`test_catmull_rom_passes_through_samples` and
`test_catmull_rom_is_c1_continuous` pin the spline math.
`test_smooth_points_length` and `test_smooth_points_memory_budget`
pin the oversampler. `test_max_displacement_bound_on_smooth_playback`
locks the max < 2x median displacement contract.
`test_seek_arc_length_per_frame_cost_under_budget` keeps the seek
cost under 5 ms.

For a visual A/B, run the validator with and without `--linear`:

```
python tools/validate_smoothness.py            # SMOOTH
python tools/validate_smoothness.py --linear   # LINEAR baseline
```

The polyline-body max segment-angle should be under 5° in SMOOTH
mode and roughly 15–25° in LINEAR mode. If the SMOOTH ratio
regresses, something has broken the Catmull-Rom path.

## Memory and perf budget

| Trajectory size | Dense buffer | Per-frame seek |
| --------------- | ------------ | -------------- |
| 1 000 samples   |     94 KB    |   < 0.5 ms     |
| 2 400 samples   |    225 KB    |   < 1 ms       |
| 10 000 samples  |    960 KB    |   < 2 ms       |

The dense buffer is computed once at prerender time and reused for
the entire playback session. The arc-length table over the dense
buffer is `(N - 1) * factor + 1` floats — negligible.

## What we did NOT change

- The PyVista / VTK attach pattern.
- The `_PrerenderWorker` QThread, the loading bar, the
  `_PRERENDER_MIN_FRAMES` threshold.
- The transport panel, scrubber, time label, status bar.
- The video-export pipeline.
- The 60 Hz `_base_tick_ms = 16` cadence — only the *meaning* of each
  tick changed (now wall-clock anchored, not stride-accumulating).
