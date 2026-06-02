r"""Closed ``(a, b)`` parameter-path generation + loop-frame precompute (CSC-005).

Drives the Conradi panel's animation: a **closed** parametric curve
``(a(t), b(t))`` swept over ``t in [0, 1)`` and the density render recomputed per
frame. Because the curve is closed (``param_loop(0) == param_loop(1)`` to machine
precision) the first and last frames meet, so the GIF / MP4 loops seamlessly.

The curve is a truncated-Fourier / epicycle series: a fundamental ellipse bent
into a "lumpy teardrop" by a couple of decaying harmonics, rigidly rotated and
recentred anywhere in ``[0, 2*pi]^2``. Every term is ``cos(k * 2*pi*t)`` /
``sin(k * 2*pi*t)``, which is identical at ``t = 0`` and ``t = 1`` — that is what
makes the loop seamless by construction.

.. note::

   Conradi's notebook (``Nice_orbits.ipynb``) renders only stills; it has no
   ``(a, b)`` path. This Fourier ``param_loop`` is the reconstructed animation
   mechanism described in ``.claude/notes/conradi-analysis/math-parameterization.md``
   (a closed parametric curve through 2-parameter space sampled per frame), with
   defaults placing the loop where the notebook's example ``(5.46, 4.55)`` lives.

Flicker control (the CSC-002 contract): each frame is an independent density
estimate, so the ``log`` tone map must use a **single fixed** ``count_max`` across
the whole loop, established by a pre-scan, rather than re-normalizing per frame.
:func:`precompute_loop_frames` does exactly that.

References
----------
- Closed-curve / truncated-Fourier parameterization of a smooth loop (the
  ``param_loop`` derivation in
  ``.claude/notes/conradi-analysis/math-parameterization.md``); the
  seamless-loop animation pattern follows Conradi's posted animations.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

from chaotic_systems.core.base import FloatArray
from chaotic_systems.visualization import attractor_density

_TWO_PI: float = 2.0 * math.pi

# Default loop shape, eyeballed from Conradi's inset and centred on the
# notebook's example (5.46, 4.55) (flagged estimate in the analysis note).
DEFAULT_CENTER: tuple[float, float] = (5.4, 4.4)
DEFAULT_RADIUS: tuple[float, float] = (0.9, 0.7)
#: Per-harmonic (amp_a, amp_b) added on top of the fundamental, starting at
#: k = 2, to bend the base ellipse into a teardrop.
DEFAULT_HARMONICS: tuple[tuple[float, float], ...] = ((0.35, -0.20), (0.12, 0.08))
DEFAULT_ROTATION: float = 0.6

#: Frames per loop for the interactive panel default. The analysis note suggests
#: 120-360 for a final export; 48 keeps the panel precompute snappy.
DEFAULT_N_FRAMES: int = 48
#: Minimum number of frames sampled in the count_max pre-scan.
_MIN_PRESCAN: int = 4

# Clifford loop geometry (CAL-001). Clifford's (a, b) are frequencies in
# [-3, 3], NOT 2*pi-periodic phases, so its loop must NOT wrap (wrap=False) and
# is centred inside the parameter range. Centre (-1.4, 1.6) is Bourke's default
# Clifford regime; radius (0.8, 0.8) with no harmonics keeps the swept
# a in [-2.2, -0.6], b in [0.8, 2.4] strictly inside [-3, 3].
CLIFFORD_LOOP_CENTER: tuple[float, float] = (-1.4, 1.6)
CLIFFORD_LOOP_RADIUS: tuple[float, float] = (0.8, 0.8)

#: A path callable maps a fraction ``t`` to ``(a, b)``.
PathFn = Callable[[float], tuple[float, float]]


def param_loop(
    t: float | FloatArray,
    *,
    center: tuple[float, float] = DEFAULT_CENTER,
    radius: tuple[float, float] = DEFAULT_RADIUS,
    harmonics: tuple[tuple[float, float], ...] = DEFAULT_HARMONICS,
    rotation: float = DEFAULT_ROTATION,
    wrap: bool = True,
) -> tuple[FloatArray, FloatArray]:
    r"""Closed parametric loop in ``(a, b)`` parameter space.

    Parameters
    ----------
    t
        Scalar or array fraction in ``[0, 1)``. ``t`` and ``t + 1`` give the
        same point (seamless).
    center
        ``(a0, b0)`` loop centre.
    radius
        ``(ra, rb)`` fundamental-ellipse semi-axes.
    harmonics
        Per-harmonic ``(amp_a, amp_b)`` added on top of the fundamental,
        starting at ``k = 2``, to bend the ellipse into a teardrop / heart.
    rotation
        Rigid rotation of the whole loop in the ``(a, b)`` plane (radians).
    wrap
        If ``True`` (default), reduce the output into ``[0, 2*pi)`` — correct
        for the Conradi map, whose ``a, b`` are 2*pi-periodic phase shifts. Set
        ``False`` for a map whose parameters are NOT periodic (e.g. Clifford's
        ``a, b`` frequencies in ``[-3, 3]``, CAL-001): the raw ``center + d``
        values are returned. Seamlessness (``loop(0) == loop(1)``) holds in both
        modes — every term is periodic in ``t`` — so ``wrap`` only changes the
        output range, never the closure.

    Returns
    -------
    tuple
        ``(a, b)``. Wrapped into ``[0, 2*pi)`` when ``wrap`` is ``True``,
        otherwise the raw values. Same shape as ``t``.
    """
    th = _TWO_PI * np.asarray(t, dtype=np.float64)

    da = radius[0] * np.cos(th)  # fundamental (k = 1)
    db = radius[1] * np.sin(th)
    for k, (amp_a, amp_b) in enumerate(harmonics, start=2):
        da = da + amp_a * np.cos(k * th)
        db = db + amp_b * np.sin(k * th)

    cos_r, sin_r = math.cos(rotation), math.sin(rotation)  # rigid rotation
    da, db = cos_r * da - sin_r * db, sin_r * da + cos_r * db

    a = center[0] + da
    b = center[1] + db
    if wrap:
        a = a % _TWO_PI
        b = b % _TWO_PI
    return a, b


def clifford_param_loop(
    t: float | FloatArray,
    *,
    center: tuple[float, float] = CLIFFORD_LOOP_CENTER,
    radius: tuple[float, float] = CLIFFORD_LOOP_RADIUS,
) -> tuple[FloatArray, FloatArray]:
    """Non-wrapping closed loop for the Clifford map's ``(a, b)`` (CAL-001).

    A plain (no-harmonic, no-rotation) ellipse centred in ``[-3, 3]^2`` with
    ``wrap=False`` so the frequencies are not folded by the Conradi ``% 2*pi``.
    Seamless by construction (``clifford_param_loop(0) == clifford_param_loop(1)``).
    """
    return param_loop(
        t, center=center, radius=radius, harmonics=(), rotation=0.0, wrap=False
    )


def precompute_loop_frames(
    n_frames: int = DEFAULT_N_FRAMES,
    *,
    path_fn: PathFn | None = None,
    map_fn: attractor_density.MapFn | None = None,
    extent: tuple[float, float, float, float] | None = None,
    n_points: int = attractor_density.DEFAULT_N_POINTS,
    n_iter: int = attractor_density.DEFAULT_N_ITER,
    bins: int = attractor_density.DEFAULT_BINS,
    gamma: float = attractor_density.DEFAULT_GAMMA,
    cmap_name: str = "magma",
    bloom: bool = False,
    prescan_frames: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[list[np.ndarray], list[tuple[float, float]], float]:
    """Render a seamless loop of density frames with a fixed brightness scale.

    Samples the closed path at ``t = i / n_frames`` for ``i in [0, n_frames)``
    (the endpoint is excluded so playback ``..., n-1, 0, 1, ...`` is seamless),
    then renders each ``(a, b)`` with the ``log`` tone map. To stop the
    brightness from flickering frame-to-frame, a single ``count_max`` is fixed up
    front by a pre-scan over a subset of frames (at the full ``bins`` so the
    scale is valid) and held constant for every frame — the CSC-002 contract.

    Parameters
    ----------
    n_frames
        Number of frames in the loop.
    path_fn
        ``t -> (a, b)``; defaults to :func:`param_loop` with the default shape.
    map_fn
        Vectorized map ``(x, y, a, b) -> (x', y')`` forwarded to the renderer;
        defaults to the Conradi map. Pass ``make_clifford_map_fn(c, d)`` (with the
        matching ``extent``) to precompute a Clifford loop.
    extent
        Render window ``(xmin, xmax, ymin, ymax)``; defaults to the Conradi
        ``[-1, 1]^2`` box. Use ``clifford_extent(c, d)`` for a Clifford map.
    n_points, n_iter, bins, gamma, cmap_name, bloom
        Render settings passed through to
        :func:`chaotic_systems.visualization.attractor_density.render`.
    prescan_frames
        How many evenly-spaced frames to accumulate when fixing ``count_max``.
        Defaults to ``max(4, n_frames // 8)``.
    progress
        Optional ``progress(done, total)`` callback invoked before each frame
        render (and once at the end). May raise to abort a long precompute.

    Returns
    -------
    frames : list of numpy.ndarray
        ``n_frames`` RGBA ``(bins, bins, 4)`` uint8 images.
    ab : list of tuple
        The ``(a, b)`` value of each frame.
    count_max : float
        The single accumulation ceiling used for every frame's tone map.
    """
    if n_frames < 1:
        raise ValueError(f"n_frames must be >= 1, got {n_frames}")
    if path_fn is None:
        path_fn = param_loop
    if map_fn is None:
        map_fn = attractor_density.conradi_map
    if extent is None:
        extent = attractor_density.DEFAULT_EXTENT

    ts = np.linspace(0.0, 1.0, n_frames, endpoint=False)
    ab: list[tuple[float, float]] = []
    for t in ts:
        a, b = path_fn(float(t))
        ab.append((float(a), float(b)))

    # Fix count_max from a pre-scan at the full bins (so the scale is valid for
    # the real render), over an evenly-spaced subset of frames.
    if prescan_frames is None:
        prescan_frames = max(_MIN_PRESCAN, n_frames // 8)
    prescan_frames = min(prescan_frames, n_frames)
    scan_idx = np.unique(
        np.linspace(0, n_frames - 1, prescan_frames).astype(np.int64)
    )
    count_max = 0.0
    for j in scan_idx:
        a, b = ab[int(j)]
        counts = attractor_density.accumulate(
            a,
            b,
            n_points=n_points,
            n_iter=n_iter,
            bins=bins,
            extent=extent,
            map_fn=map_fn,
        )
        count_max = max(count_max, float(counts.max()))
    count_max = max(count_max, 1.0)

    frames: list[np.ndarray] = []
    for i, (a, b) in enumerate(ab):
        if progress is not None:
            progress(i, n_frames)
        rgba = attractor_density.render(
            a,
            b,
            n_points=n_points,
            n_iter=n_iter,
            bins=bins,
            extent=extent,
            tone="log",
            gamma=gamma,
            cmap_name=cmap_name,
            bloom=bloom,
            count_max=count_max,
            map_fn=map_fn,
        )
        frames.append(rgba)
    if progress is not None:
        progress(n_frames, n_frames)
    return frames, ab, count_max


__all__ = [
    "CLIFFORD_LOOP_CENTER",
    "CLIFFORD_LOOP_RADIUS",
    "DEFAULT_CENTER",
    "DEFAULT_HARMONICS",
    "DEFAULT_N_FRAMES",
    "DEFAULT_RADIUS",
    "DEFAULT_ROTATION",
    "PathFn",
    "clifford_param_loop",
    "param_loop",
    "precompute_loop_frames",
]
