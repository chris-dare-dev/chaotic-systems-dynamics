# Renderer animation performance notes

This document captures the bug taxonomy, measurements, and design choices
behind the second renderer-performance pass on `Renderer3D`. Read this
alongside `src/chaotic_systems/visualization/renderer.py`.

## The two visible problems

1. **"Dot cloud" artifact.** While the polyline grew during playback, the
   user saw the *entire* trajectory pre-drawn as a Lorenz-attractor-shaped
   cloud of viridis-colored dots. The polyline-tail then grew correctly
   over the cloud — but the cloud was always there from frame 1.

2. **Animation felt jittery / not smooth.** Even after the prior 60 Hz
   timer + sub-frame head interpolation + dense `t_eval` pass, the
   playback had a "ratcheting" feel: the head sphere glided smoothly but
   the polyline tail snapped between integer trajectory samples in
   discrete jumps.

## Root causes

### Problem A — dot cloud is `pv.PolyData`'s default vertex cells

```python
poly = pv.PolyData(points)
print(poly.n_verts)  # == len(points)
```

`pv.PolyData(points)` populates a vertex cell per input point in addition
to whatever line/face cells you later attach. VTK's mapper happily
renders those vertex glyphs as visible points, colored by whatever
point-data scalar is attached (in our case the `time` linspace, which
maps directly through the viridis colormap). The trajectory polyline
itself was correct — but the orphan vertex cells masquerade as a static
trajectory cloud underneath.

**Fix:** clear the verts cell array immediately after construction:

```python
polyline.verts = np.empty(0, dtype=np.int64)
```

This is the structurally-correct fix (a polyline-only PolyData should
have zero vertex cells). It costs nothing per frame and is locked in by
`tests/visualization/test_animation.py::test_polydata_has_no_verts_after_build`.

### Problem B Fix 1 — sub-frame polyline tail

The pre-existing `seek_interpolated(idx_float)` interpolated the *head
sphere* between samples `i` and `i+1`, but the polyline still
short-circuited to the integer-floor `_set_visible_points(i + 1)`. With
the per-tick stride capped at 4, this meant the head glided smoothly
while the polyline jumped a four-sample chunk every render — visually
that's worse than not interpolating the head at all.

**Fix:** allocate the PolyData with one extra "tail" point slot. Each
fractional `seek_interpolated` call writes the interpolated head position
into the tail-slot row (in place — VTK-backed numpy view, single-row
mutation) and sets a connectivity slice of the form
`[count, 0, 1, ..., i, tail_index]`. The polyline now draws the integer
prefix plus a final fractional segment to the lerped head point. The
head sphere sits on top of that lerped point. Polyline and head move
together, sub-frame.

The `_current_n` field still tracks the *integer prefix count* (`i + 1`)
so `current_frame`, the scrubber, and the transport bookkeeping behave
exactly as before — `seek_interpolated(2.5)` reports `current_frame == 3`
and `head_position == points[2]`, while the *tail point* of the polyline
and the head actor are both at `0.5 * (points[2] + points[3])`.

### Problem B Fix 2 — pre-allocated connectivity buffer

`_full_polyline_connectivity(n)` used to allocate a fresh
`np.empty(n + 1)` and a fresh `np.arange(n)` *every frame*. At 60 Hz
with a 4000-sample Lorenz trajectory that's ~480k integer-element
allocations per second of playback plus the temporary `np.arange` on
top — measurable GC pressure with no payoff.

**Fix:** the renderer now owns a single `_connectivity_buffer` of size
`N + 2` (worst case: header byte + every integer index + tail). Each
frame writes the count into `buf[0]` and slices `buf[:n+1]` or
`buf[:i+3]` to hand VTK only the active prefix. The integer-index span
`buf[1:N+1]` is written once at `_build_scene` time and never touched
again unless the active prefix grows past the previous high-water mark.

Benchmark (1000 iterations on the connectivity allocation path alone):

```
Old (np.empty + arange per frame): 0.73 us/frame
New (pre-alloc + slice):           0.19 us/frame
```

~4x faster on the connectivity-update path and zero per-frame
allocations.

### Problem B Fix 3 — `add_mesh` ghost-actor audit

`set_line_width` and `set_color_by_progress` both rebuild the line
actor by calling `add_mesh` with a new `line_width` / `cmap` config.
Both *do* call `remove_actor(self._line_actor, render=False)` before the
re-add, so they don't accumulate ghost actors. Verified by direct
inspection of `plotter.renderer.actors` count across repeated calls,
and pinned in `tests/visualization/test_animation.py::test_set_line_width_does_not_increase_actor_count`.

### Problem B Fix 4 — frame timing

End-to-end frame cost on an off-screen `pv.Plotter` (Apple Silicon,
no Retina compositor in the loop):

```
integer seek + render:          0.781 ms/frame  (~1280 FPS)
fractional seek_interpolated:   0.863 ms/frame  (~1159 FPS)
```

Both code paths sit well under the 16.6 ms budget of a 60 Hz tick. The
attached-QtInteractor case is bounded by the compositor's vsync, not by
VTK. The "jittery" feel the user reported was visual, not throughput-
limited — Fix 1 (sub-frame polyline tail) addresses the actual
discontinuity, not Fix 2 / Fix 4.

### Problem B Fix 5 — re-attach actor leaks

`Renderer3D.attach(qt_interactor)` calls `_build_scene` against the new
plotter. The PolyData and head sphere are *re-built* fresh (assigned
to `self._polyline` / `self._head_actor`), and the previous plotter's
references go out of scope along with the previous plotter itself.
PyVista's `QtInteractor.clear()` (called by the GUI before re-attach)
removes the previous plotter's actors. No leak in the current code path
— but the prerender cache (`_arc_lengths`, `_prerender_built`) IS
invalidated on re-attach so the GUI's warm-up loop will re-run.

## GUI-side change

With sub-frame interpolation on both the polyline tail and the head
sphere, the per-tick stride cap drops from `4` to `2`. At
`target_playback_seconds = 15.0` and `_base_tick_ms = 16`, the ideal
stride for a 1500-sample trajectory is ~1.6 — comfortably under 2. For
dense trajectories that would otherwise demand stride > 2, playback
just runs slightly longer than the 15 s target, which is the right
trade-off (fluid motion beats hitting an exact wall-clock target).

The `n_points` request in `_on_run` is bumped from ~38 samples/sec to
~60 samples/sec to match this: 60 samples × 15 s × 1 stride/sample =
900 ticks, exactly the 60 Hz × 15 s budget.

## Tests

Locked-in invariants added under `tests/visualization/test_animation.py`:

- `test_polydata_has_no_verts_after_build` — dot-artifact regression.
- `test_seek_interpolated_tail_is_midpoint` — sub-frame tail correctness.
- `test_set_line_width_does_not_increase_actor_count` — ghost-actor audit.

The existing 11 animation tests plus the 13 prerender tests (from the
parallel pre-render pipeline pass) continue to pass.

## What's *not* changed

- The `_full_polyline_connectivity` free function still exists for
  backward compatibility; tests that hold references to it keep working.
  Internal callers route through `_make_integer_connectivity` (which
  slices the pre-allocated buffer).
- `head_position` still returns the *integer-floor* sample by default —
  the public contract the transport scrubber and the
  `test_seek_interpolated_lerps_head_position` test rely on. The
  arc-length seek path overrides it to the lerped world position via
  `_head_world_pos` (a hook the prerender pass added).
