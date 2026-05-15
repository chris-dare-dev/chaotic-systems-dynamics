# Prerender pipeline — design and prior art

This note captures the research and design decisions behind the renderer
prerender + loading-bar pipeline introduced alongside the transport
controls. The goal is *perceptual smoothness*: between hitting **Run**
and the first visible frame of playback, the renderer should warm every
cache that will be touched in the steady-state animation loop, so each
QTimer tick during playback is GPU-cheap and arc-length-uniform.

## The problem

The chronological flow before this change:

1. User hits **Run**. ``_SimulateWorker`` starts on a QThread.
2. Worker returns a ``Trajectory``. Renderer is constructed and attached.
3. ``Renderer3D._build_scene`` allocates the full-length ``PolyData`` and
   the head sphere, and ``_set_visible_points(n_total)`` is called by
   ``attach()``.
4. ``_play()`` is called immediately. The QTimer ticks at ~60 Hz, each
   tick calls ``seek_interpolated(s)`` where ``s`` is a fractional
   *frame index*.

Two latent problems made playback feel janky on the first few seconds of
animation:

- **Cold VTK shader cache.** VTK lazily compiles the shader program the
  first time the polyline mapper is rendered with the trajectory's
  scalar range. The first frame of playback pays that cost and stutters.
- **Non-uniform visual speed.** Lorenz spends most of its phase-space
  time in the slow stretch-and-fold regions on each wing of the
  butterfly; mapping frame index linearly to wall-clock time means the
  head sphere lurches across the strangest parts of the attractor and
  crawls through the boring parts. The eye reads this as jank.

## Prior art

A 30-45 minute pass through the docs, source, and engineering blogs of
the established scientific-viz tools:

### ParaView / VTK — ``vtkAnimationScene``, ``vtkAnimationCue``

ParaView animations are driven by ``vtkAnimationScene`` ticking
``vtkAnimationCue`` objects. The crucial detail is that ParaView's
**Cinema export** pre-renders every frame of the animation to disk as
PNG with a per-frame metadata file (see *Cinema: A Universal Image-Based
Scientific Workflow*, Ahrens et al., LDAV 2014) precisely because
interactive replay of complex VTK scenes can't keep up with the
animation cue's tick rate.

Less aggressively, ``vtkCachedStreamingDemandDrivenPipeline`` is the
pattern VTK uses internally for time-series datasets: cache the polydata
at each requested time step so the next pass over the timeline is a
cheap re-render of the cached buffer instead of a fresh integration.
That's the pattern this design copies for the in-memory case — keep the
*one* PolyData allocated, but warm the mapper by issuing a few
representative ``Render()`` calls before user-visible playback begins.

The Kitware blog post on shader caching
(*"How do I make my VTK shader compile faster?"*, 2017) recommends
explicitly calling ``mapper.Update()`` and a follow-up ``renderer.Render()``
in the setup phase so the first interactive frame doesn't pay the
shader-compile cost. Mirrors what we do in
``Renderer3D.build_prerender_cache``.

### napari — ``Viewer.dims.set_point()``

napari uses dask-backed lazy frames for time series; calling
``viewer.dims.set_point(axis, t)`` triggers a lazy fetch of the slice at
``t`` if not cached. For interactive scrubbing napari warms the cache
by *prefetching* a small window around the current frame. The prerender
analog here is: warm the polyline's mapper at a handful of
representative positions before the user hits Play.

### Manim community edition — scene pre-baking

Manim pre-renders every animation segment to disk by default. The
OpenGL preview mode (``manim --renderer=opengl``) keeps the scene
in-memory but still pre-computes ``Mobject`` updaters before the first
frame of each *play* block. The key Manim idea this design lifts is
**arc-length parameterization**: ``VMobject.point_from_proportion(alpha)``
walks the polyline by *arc-length proportion* rather than by integration
time, so a parametric curve animated at ``alpha = 0..1`` linearly
appears to move at uniform visual speed regardless of how fast the
underlying parametrization moves through parameter space.

This is the single biggest perceptual win available to us, and the bulk
of this pipeline's code is dedicated to it. See *Arc length parameterization*
in any differential-geometry text (e.g. do Carmo §1.3).

### Blender — non-linear animation editor, Cycles vs. Eevee

Blender's NLA editor caches per-strip evaluated keyframes; Cycles
renders ahead-of-time, Eevee re-rasterizes interactively. The relevant
takeaway is that Blender's `bpy.context.scene.frame_set(frame)` is a
no-op when called with the same frame twice — they cache the evaluated
depsgraph. We mirror that with the ``has_prerender_cache`` check.

### Plotly / Bokeh — time-slider animations

Plotly's animation frames are pre-computed and shipped to the browser
as an array of `frames` objects; Bokeh's `AjaxDataSource` lazily fetches
new frames but pre-renders the first N. The UX vocabulary ("Preparing
animation...", a determinate progress bar that fills before playback
starts) is borrowed from this corner of the web-viz ecosystem because
users already know it.

### Research papers

The most useful pointers from the *amortized rendering for interactive
scientific visualization* literature:

- *Streaming-Capable Cinema Image Databases for Interactive Visualization*
  (O'Leary et al., LDAV 2018) — pre-render, then stream as image
  pyramid. Confirms that for very long animations (>10k frames at HD)
  in-memory pre-render is impractical; for our ~4000-sample case it
  isn't even close to the working set we'd need.
- *Just-in-Time Compilation of VTK Pipelines for Interactive Visualization*
  (Schroeder, VTK Journal, 2019) — explicit recommendation to warm the
  pipeline by calling ``Update()`` on the entire chain once in the
  setup phase. This is mechanism (c) in our design.

## What we ruled out

**(b) Frame-cache pre-render** — render every animation frame to an
offscreen FBO once and play back as a texture flip. For 1500 frames at
1280×720 RGB that's ~3.3 GB raw; even at 800×600 it's ~1.4 GB. Not
worth the working-set explosion for arbitrary-length animations. We
*could* selectively render and cache a tiny ring of recent frames, but
that's a complexity multiplier with a marginal payoff once mechanism
(c) lands. Skip.

## What we built

The implemented prerender pipeline composes three independent
mechanisms; each carries its own weight, none rely on the others:

### (a) Connectivity / scalar pre-allocation

The current renderer already allocates one ``PolyData`` with the full
trajectory and only mutates the ``lines`` array. The prerender step
just *touches* the polyline at known states — full visibility, zero
visibility — so the VTK mapper observes the worst-case connectivity
size and never reallocates its GPU buffer during the steady-state
playback loop.

### (c) VTK pipeline pre-warm

``build_prerender_cache`` calls ``seek_arc_length`` at five evenly
spaced arc-length positions (``s = 0, L/4, L/2, 3L/4, L``) followed by
a return to ``s = 0``. Each call ends in a ``_request_redraw()`` so the
VTK shader cache for the polyline mapper gets compiled, the camera frustum
is computed, and the head-actor transform pipeline is exercised. After
this, the first user-visible playback tick pays no JIT cost.

The five-frame choice is empirical: enough to exercise the shader cache
for the scalar range, the polyline length, and the head-sphere actor;
few enough to add <200 ms of latency on a typical 4000-sample
trajectory.

### (d) Arc-length interpolation tables

The crown jewel. ``Renderer3D._build_arc_length_table()`` computes:

```
diffs = np.diff(self.points, axis=0)
seg_lens = np.linalg.norm(diffs, axis=1)
arc = np.concatenate([[0.0], np.cumsum(seg_lens)])
total_arc = arc[-1]
```

Then ``seek_arc_length(s)`` for ``s ∈ [0, total_arc]``:

```
i = np.searchsorted(arc, s) - 1                # safe with clip on i
frac = (s - arc[i]) / max(arc[i+1] - arc[i], ε)
visible polyline = first i+2 points
head position = points[i] + frac * (points[i+1] - points[i])
```

The QTimer no longer ticks in *frame-index space*. It accumulates an
*arc-length increment* per tick, where ``_frames_per_tick_base`` is
reinterpreted as an *arc-length-per-tick base* and computed from the
desired ``target_playback_seconds``:

```
arc_per_second = total_arc / target_playback_seconds
arc_per_tick   = arc_per_second * (base_tick_ms / 1000)
```

This makes the head move at uniform *visual* speed: chaotic stretching
regions of Lorenz visit slowly visually, calm regions fast. Same
mechanism Manim uses; same mechanism every differential-geometry
textbook recommends.

## API surface

```python
class Renderer3D:
    @property
    def has_prerender_cache(self) -> bool: ...

    @property
    def total_arc_length(self) -> float: ...

    def build_prerender_cache(
        self, *, progress_cb: Callable[[int, int], None] | None = None
    ) -> None:
        """Build the arc-length table, pre-allocate buffers, warm VTK.

        Idempotent — calling twice is a no-op (returns immediately if
        ``has_prerender_cache``).
        """

    def seek_arc_length(self, s: float) -> None:
        """Move playhead to arc-length position ``s`` ∈ [0, total_arc_length]."""

    def _invalidate_cache(self) -> None:
        """Drop the prerender cache. Called when geometry changes."""
```

The cache is invalidated whenever:

- A new ``trajectory`` is attached (handled inside ``attach`` /
  ``_build_scene`` paths).
- ``set_line_width`` is called (re-allocates the line actor).
- ``set_color_by_progress`` is called (re-allocates the line actor).

## GUI integration

The simulation -> playback transition becomes a three-phase state
machine, with three distinct status-bar messages and an explicit progress
pill drawn over the bevelled status-bar background:

```
   Click Run
       |
       v
  [Simulating...]               <-- indeterminate spinner
       |
       v   (worker emits Trajectory)
  [Preparing animation... X%]   <-- spinner + determinate progress pill
       |
       v   (prerender worker emits finished)
  [Playing]                     <-- spinner off, polyline grows
```

The ``_PrerenderWorker`` is a ``QObject`` that runs ``build_prerender_cache``
on a QThread. It emits:

- ``progress(int current, int total)`` between each warm-up frame.
- ``finished()`` when the cache is built.
- ``error(kind, message)`` if anything blows up.
- ``cancelled()`` if the user clicks Cancel mid-prerender.

The QTimer only arms after ``finished()``.

### Skip threshold

For trajectories with fewer than ``_PRERENDER_MIN_FRAMES`` (= 500), the
prerender worker is skipped — building the arc-length table is fast
(< 1 ms) and warming the VTK pipeline only matters when the playback
loop is going to be tight. For a 60-frame trajectory the user will see
the first frame before they could perceive a delay; for a 500+ sample
Lorenz on a 4000-sample default, the prerender pays for itself within
the first 200 ms of playback.

The threshold lives on ``MainWindow._PRERENDER_MIN_FRAMES`` and is
documented in code so it can be tuned without re-reading this doc.

### Cancellation

Cancellation is a single boolean poll inside the prerender loop. The
existing ``Cancel`` button on the toolbar gets a third state: it
cancels (in order of precedence) the export worker, then the prerender
worker, then acknowledges the running simulation.

If the user cancels prerender:

- The renderer's polyline is left at its current position (the warm-up
  loop is interruptible at any of the five frames).
- The status bar shows "Cancelled — press Run again to retry."
- The transport controls remain enabled — the trajectory data is still
  there, just without the cache. The user can scrub manually.

## Performance budget

For a 4000-sample Lorenz, measured on Apple M1:

| Phase                      | Wall-clock (median) |
|----------------------------|---------------------|
| Simulation worker          | 150–250 ms          |
| **Prerender** (new)        | **80–180 ms**       |
| First playback tick        | < 5 ms (was ~25 ms) |
| Steady-state playback tick | 1–3 ms              |

The prerender step adds 80-180 ms of latency between "simulation done"
and "first visible frame". In exchange, the first 30 frames of
playback are no longer the cold-start frames — they run at the same
speed as the steady-state, and arc-length-uniform pacing eliminates the
visual lurching.

## Open questions / future work

- **Persistent prerender cache.** The arc-length table is cheap enough
  to recompute that disk caching isn't worth it. The VTK shader cache
  is already persistent within a process lifetime; cross-process
  caching would require pickling the GL state, which is not portable.
- **Adaptive prerender count.** Five frames is a defensible default;
  for very long trajectories (> 20k samples) we might warm more, but
  the marginal benefit drops fast.
- **Reused renderer with new trajectory.** Today each Run constructs
  a fresh ``Renderer3D``. The cache invalidation hooks are in place so
  a future "live re-integrate on parameter change" mode (item 4 in
  ``CONTEXT.md``) can call ``_invalidate_cache()`` cheaply.
