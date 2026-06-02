r"""Density-accumulation render engine for trigonometric strange-attractor art.

This is the heart of the Conradi-attractor panel (CSC-002 of
``docs/proposals/conradi-attractor-panel-2026-05-31.md``): a pure
arrays-in / RGBA-out module — no Qt — that turns map parameters into a
luminous density image on a black background, the way Simone Conradi's
``Nice_orbits.ipynb`` renders his trigonometric attractors.

The pipeline, in order:

1. **Accumulate.** Lay down an ``n_points x n_points`` lattice of initial
   conditions over the render window and iterate *every* seed ``n_iter``
   steps, binning each iterate into a high-resolution 2D histogram. This is
   Conradi's method: the structured folds come from the coherent transient
   flow of a dense IC grid, not from the ergodic mixing of a single long
   orbit. (Confirmed against ``Nice_orbits.ipynb``: ~300-500 seeds per axis,
   ~200-300 steps each, accumulated into one histogram.)
2. **Tone-map.** Raw counts span a huge dynamic range — hot cores get
   hundreds of hits, the faint outer membrane gets one or two. A strongly
   compressive transfer (``eq_hist`` / ``log`` / ``cbrt`` / ``linear``) makes
   both visible at once.
3. **Colorize.** A perceptually-uniform colormap (magma / inferno) resolved
   through :mod:`chaotic_systems.visualization.colormaps`, with empty cells
   forced to exact black so the background reads cleanly.
4. **Bloom** (optional). A multi-scale additive Gaussian halo that turns the
   blown-out white cores into luminous glow.

Performance: the accumulation loop is recursive (each iterate depends on the
last), so it cannot be vectorized over iterations. The fast path is a
``numba``-jitted fused iterate-and-accumulate kernel; when the ``[performance]``
extra is absent the module falls back to a NumPy path that vectorizes over the
lattice of seeds and loops over iterations in Python (the same graceful-degrade
contract the integrators use). The JIT kernel is run **single-threaded** on
purpose: the obvious ``parallel=True`` version races on the shared count buffer
(concurrent ``count[iy, ix] += 1`` loses updates), and single-thread numba is
already ~100-500 Mpts/s, which renders the default ~22M-point lattice in well
under a second.

References
----------
- Scott Draves & Erik Reckase (2003), *The Fractal Flame Algorithm*,
  https://flam3.com/flame_draves.pdf — the log-density display transform
  ``alpha = log(count) / log(count_max)`` (with gamma) that makes
  chaotic-orbit density images readable. Robust form uses ``log1p`` so
  ``count == 0`` maps to 0.
- N. Smith & S. van der Walt (2015), *A Better Default Colormap for
  Matplotlib*, SciPy 2015 — the perceptually-uniform magma / inferno maps,
  whose near-black low end is why the background reads as pure black.
- Simone Conradi, ``Nice_orbits.ipynb``,
  https://github.com/profConradi/Python_Simulations — the IC-lattice
  accumulation method, the ``n_points`` / ``n_iter`` / ``bins`` scales, and the
  ``clip(log1p(count), 0, 5)`` tone map reproduced here as the default ``log``
  transfer. The ``how=`` tone-map names (``eq_hist`` default, ``log`` = log1p,
  ``cbrt``, ``linear``) follow datashader's transfer-function vocabulary.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from chaotic_systems.core._numba import NUMBA_AVAILABLE, maybe_njit
from chaotic_systems.core.base import FloatArray
from chaotic_systems.visualization import colormaps

# --- Render constants (named per CLAUDE.md; no magic numbers) ----------------

#: Seeds per lattice axis. Conradi's notebook uses 300-500; 300 -> 90k seeds
#: is a good GUI/quality balance (the panel may raise it for stills).
DEFAULT_N_POINTS: int = 300
#: Iterations per seed. Notebook uses 200-300; the full transient is binned
#: (no transient discard) because the transient flow *is* the image.
DEFAULT_N_ITER: int = 250
#: Histogram resolution (output is ``bins x bins``). The notebook uses 3000 for
#: print stills; 800 keeps interactive renders responsive.
DEFAULT_BINS: int = 800
#: Gamma for the ``log`` / ``cbrt`` tone maps. >1 lifts the faint shells.
DEFAULT_GAMMA: float = 2.2

#: ``log`` tone-map clip on ``log1p(count)``, verbatim from Conradi's notebook
#: (``vmin=0, vmax=5``). A cell with ``count >= e**5 - 1 ~ 147`` saturates to
#: white. A fixed absolute ceiling makes the default ``log`` mode temporally
#: stable across an animation loop without a per-frame rescale.
VMIN: float = 0.0
VMAX: float = 5.0

#: ConradiMap self-bounds to [-1, 1]^2 after one step, so both the IC lattice
#: and the binning window live on [-IC_EXTENT, IC_EXTENT]^2.
IC_EXTENT: float = 1.0
#: Default render window (xmin, xmax, ymin, ymax) for the bounded Conradi map.
DEFAULT_EXTENT: tuple[float, float, float, float] = (
    -IC_EXTENT,
    IC_EXTENT,
    -IC_EXTENT,
    IC_EXTENT,
)

# --- Bloom constants (the multi-scale additive-halo recipe) ------------------

#: Brightness above which a cell is treated as a hot "core" that blooms.
BLOOM_THRESHOLD: float = 0.75
#: Two Gaussian scales (px): a tight inner glow and a wide soft halo.
BLOOM_SIGMAS: tuple[float, ...] = (2.0, 8.0)
#: Additive strength of the bloom blend (screen-style; only brightens).
BLOOM_STRENGTH: float = 0.8

ToneMode = Literal["eq_hist", "log", "cbrt", "linear"]
#: A vectorized map ``(x, y, a, b) -> (x_new, y_new)`` over arrays of seeds.
MapFn = Callable[
    [FloatArray, FloatArray, float, float], tuple[FloatArray, FloatArray]
]

Uint8Array = NDArray[np.uint8]

_BLACK_RGBA: tuple[int, int, int, int] = (0, 0, 0, 255)


def conradi_map(
    x: FloatArray, y: FloatArray, a: float, b: float
) -> tuple[FloatArray, FloatArray]:
    """The Conradi map ``x' = sin(x^2 - y^2 + a)``, ``y' = cos(2xy + b)``.

    Vectorized over arrays of seeds; this is the default ``map_fn`` for the
    NumPy accumulation fallback (the JIT fast path inlines the same recurrence).
    """
    return np.sin(x * x - y * y + a), np.cos(2.0 * x * y + b)


# Stable map-identity tag read by the JIT dispatch in ``accumulate`` (CMP-003).
# Keying on this string — not the function object — lets a freshly-built map_fn
# closure (e.g. ``make_clifford_map_fn(c, d)``) still reach its kernel; a plain
# identity check fails on every new closure (the AP1 pitfall).
conradi_map._map_id = "conradi"  # type: ignore[attr-defined]


# -----------------------------------------------------------------------------
# Accumulation
# -----------------------------------------------------------------------------


@maybe_njit(cache=True)
def _accumulate_lattice_jit(
    a: float,
    b: float,
    n_points: int,
    n_iter: int,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    bins: int,
) -> FloatArray:
    """Fused iterate-and-accumulate for the Conradi recurrence (numba fast path).

    Single-threaded by design — a ``parallel=True`` variant would race on the
    shared ``count`` buffer. Bins *every* iterate of every seed; for the bounded
    Conradi map all iterates land in-window, so the total mass is exactly
    ``n_points**2 * n_iter``.
    """
    count = np.zeros((bins, bins), np.float64)
    sx = (bins - 1) / (xmax - xmin)
    sy = (bins - 1) / (ymax - ymin)
    dx = (xmax - xmin) / (n_points - 1)
    dy = (ymax - ymin) / (n_points - 1)
    for i in range(n_points):
        seed_x = xmin + dx * i
        for j in range(n_points):
            x = seed_x
            y = ymin + dy * j
            for _ in range(n_iter):
                x_new = np.sin(x * x - y * y + a)
                y_new = np.cos(2.0 * x * y + b)
                x, y = x_new, y_new
                ix = int((x - xmin) * sx)
                iy = int((y - ymin) * sy)
                if 0 <= ix < bins and 0 <= iy < bins:
                    count[iy, ix] += 1.0
    return count


@maybe_njit(cache=True)
def _accumulate_clifford_jit(
    a: float,
    b: float,
    c: float,
    d: float,
    n_points: int,
    n_iter: int,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    bins: int,
) -> FloatArray:
    """Fused iterate-and-accumulate for the Clifford recurrence (numba fast path).

    Clifford map ``x' = sin(a y) + c cos(a x)``, ``y' = sin(b x) + d cos(b y)``
    (CSC-008). Single-threaded by design — like the Conradi kernel, a
    ``parallel=True`` variant would race on the shared ``count`` buffer. The map
    is bounded to ``[-(1+|c|), 1+|c|] x [-(1+|d|), 1+|d|]`` (= the passed extent),
    so every iterate lands in-window and the total mass is exactly
    ``n_points**2 * n_iter``.
    """
    count = np.zeros((bins, bins), np.float64)
    sx = (bins - 1) / (xmax - xmin)
    sy = (bins - 1) / (ymax - ymin)
    dx = (xmax - xmin) / (n_points - 1)
    dy = (ymax - ymin) / (n_points - 1)
    for i in range(n_points):
        seed_x = xmin + dx * i
        for j in range(n_points):
            x = seed_x
            y = ymin + dy * j
            for _ in range(n_iter):
                x_new = np.sin(a * y) + c * np.cos(a * x)
                y_new = np.sin(b * x) + d * np.cos(b * y)
                x, y = x_new, y_new
                ix = int((x - xmin) * sx)
                iy = int((y - ymin) * sy)
                if 0 <= ix < bins and 0 <= iy < bins:
                    count[iy, ix] += 1.0
    return count


def _accumulate_lattice_numpy(
    map_fn: MapFn,
    a: float,
    b: float,
    n_points: int,
    n_iter: int,
    extent: tuple[float, float, float, float],
    bins: int,
) -> FloatArray:
    """Pure-NumPy accumulation: vectorize over seeds, loop over iterations.

    Mirrors :func:`_accumulate_lattice_jit`'s index convention
    (``int((x - xmin) * sx)``, drop out-of-window) so the two paths produce the
    same total mass and near-identical structure. Used when numba is absent, or
    for a non-Conradi ``map_fn``.
    """
    xmin, xmax, ymin, ymax = extent
    xs = np.linspace(xmin, xmax, n_points)
    ys = np.linspace(ymin, ymax, n_points)
    grid_x, grid_y = np.meshgrid(xs, ys)
    x = grid_x.ravel().astype(np.float64)
    y = grid_y.ravel().astype(np.float64)

    count = np.zeros((bins, bins), np.float64)
    flat = count.ravel()
    sx = (bins - 1) / (xmax - xmin)
    sy = (bins - 1) / (ymax - ymin)
    for _ in range(n_iter):
        x, y = map_fn(x, y, a, b)
        ix = ((x - xmin) * sx).astype(np.int64)
        iy = ((y - ymin) * sy).astype(np.int64)
        in_window = (ix >= 0) & (ix < bins) & (iy >= 0) & (iy < bins)
        np.add.at(flat, iy[in_window] * bins + ix[in_window], 1.0)
    return count


# Per-map JIT accumulator registry (CMP-003) — the "variation dispatch" of the
# fractal-flame architecture (Draves & Reckase 2003): one accumulation loop per
# map, selected by the map's stable ``_map_id`` tag rather than by the closure
# object. Each adapter calls the right ``@maybe_njit`` kernel with the map's
# secondary parameters (from ``map_fn._map_params``). Adding a future art-map is
# one kernel + one registry entry, with no change to ``accumulate``/``render``.
_JitAccumulator = Callable[
    [float, float, tuple[float, ...], int, int, tuple[float, float, float, float], int],
    FloatArray,
]


def _conradi_jit_accumulate(
    a: float,
    b: float,
    map_params: tuple[float, ...],
    n_points: int,
    n_iter: int,
    extent: tuple[float, float, float, float],
    bins: int,
) -> FloatArray:
    return _accumulate_lattice_jit(a, b, n_points, n_iter, *extent, bins)


def _clifford_jit_accumulate(
    a: float,
    b: float,
    map_params: tuple[float, ...],
    n_points: int,
    n_iter: int,
    extent: tuple[float, float, float, float],
    bins: int,
) -> FloatArray:
    c, d = map_params
    return _accumulate_clifford_jit(
        a, b, float(c), float(d), n_points, n_iter, *extent, bins
    )


_JIT_ACCUMULATORS: dict[str, _JitAccumulator] = {
    "conradi": _conradi_jit_accumulate,
    "clifford": _clifford_jit_accumulate,
}


def accumulate(
    a: float,
    b: float,
    *,
    n_points: int = DEFAULT_N_POINTS,
    n_iter: int = DEFAULT_N_ITER,
    bins: int = DEFAULT_BINS,
    extent: tuple[float, float, float, float] = DEFAULT_EXTENT,
    map_fn: MapFn = conradi_map,
    use_numba: bool | None = None,
) -> FloatArray:
    """Accumulate the IC-lattice density histogram for ``map_fn`` at ``(a, b)``.

    Returns a ``(bins, bins)`` float64 count field. Dispatches to the numba fast
    path when available *and* ``map_fn`` carries a ``_map_id`` registered in
    :data:`_JIT_ACCUMULATORS` (Conradi and Clifford today); otherwise uses the
    NumPy fallback over ``map_fn`` (which works for any callable). ``use_numba``
    overrides the auto-decision; forcing ``True`` on a map with no registered
    kernel still falls back to NumPy rather than running the wrong recurrence.
    """
    map_id = getattr(map_fn, "_map_id", None)
    jit = _JIT_ACCUMULATORS.get(map_id) if isinstance(map_id, str) else None
    if use_numba is None:
        use_numba = NUMBA_AVAILABLE and jit is not None
    if use_numba and jit is not None:
        map_params: tuple[float, ...] = getattr(map_fn, "_map_params", ())
        return jit(a, b, map_params, n_points, n_iter, extent, bins)
    return _accumulate_lattice_numpy(
        map_fn, a, b, n_points, n_iter, extent, bins
    )


# -----------------------------------------------------------------------------
# Tone mapping
# -----------------------------------------------------------------------------


def tone_map(
    count: FloatArray,
    mode: ToneMode = "eq_hist",
    *,
    gamma: float = DEFAULT_GAMMA,
    count_max: float | None = None,
) -> FloatArray:
    """Map a count field to a brightness field in ``[0, 1]``.

    ``count == 0`` cells always map to 0 (black background). Modes:

    - ``eq_hist`` — rank/CDF equalization of the non-zero counts; parameter-free
      and the closest match to Conradi's stills (datashader's default).
    - ``log`` — ``log1p`` density display (Draves & Reckase). With no
      ``count_max`` this uses the notebook-faithful absolute clip
      ``clip(log1p(count), VMIN, VMAX) / VMAX`` (a fixed scale, so it does not
      flicker across animation frames). Passing ``count_max`` switches to the
      adaptive flame normalization ``log1p(count) / log1p(count_max)`` — use a
      single pre-scanned ``count_max`` across an animation loop (CSC-005).
    - ``cbrt`` — cube-root of the normalized count; a milder compression.
    - ``linear`` — normalized count; the faint shells vanish (diagnostic only).

    The ``gamma`` exponent applies to ``log`` and ``cbrt`` (>1 lifts shadows).
    """
    bright = np.zeros_like(count, dtype=np.float64)
    nonzero = count > 0
    if not nonzero.any():
        return bright

    if mode == "eq_hist":
        values = count[nonzero]
        order = np.argsort(values, kind="stable")
        ranks = np.empty(order.size, dtype=np.float64)
        ranks[order] = np.arange(1, order.size + 1, dtype=np.float64)
        bright[nonzero] = ranks / order.size
        return bright

    if mode == "log":
        if count_max is None:
            # Notebook-faithful fixed absolute scale (vmin=0, vmax=5).
            bright = np.clip(np.log1p(count), VMIN, VMAX) / VMAX
        else:
            # Flame adaptive normalization against a (possibly fixed) ceiling.
            denom = np.log1p(max(count_max, 1.0))
            bright = np.log1p(count) / denom
        return np.clip(bright, 0.0, 1.0) ** (1.0 / gamma)

    ceiling = count_max if count_max is not None else float(count.max())
    ceiling = max(ceiling, 1.0)
    if mode == "cbrt":
        bright[nonzero] = (count[nonzero] / ceiling) ** (1.0 / 3.0)
        return np.clip(bright, 0.0, 1.0) ** (1.0 / gamma)
    if mode == "linear":
        bright[nonzero] = count[nonzero] / ceiling
        return np.clip(bright, 0.0, 1.0)

    raise ValueError(
        f"unknown tone mode {mode!r}; expected one of "
        "'eq_hist', 'log', 'cbrt', 'linear'"
    )


# -----------------------------------------------------------------------------
# Bloom
# -----------------------------------------------------------------------------


def apply_bloom(
    bright: FloatArray,
    *,
    threshold: float = BLOOM_THRESHOLD,
    sigmas: tuple[float, ...] = BLOOM_SIGMAS,
    strength: float = BLOOM_STRENGTH,
) -> FloatArray:
    """Add a multi-scale Gaussian bloom to a brightness field.

    Isolates the hottest cores (``bright > threshold``), blurs them at several
    scales, and adds the halo back (screen-style — only brightens). Returns a
    new ``[0, 1]`` brightness field. Requires :mod:`scipy.ndimage`.
    """
    from scipy.ndimage import gaussian_filter

    core = np.clip(bright - threshold, 0.0, 1.0)
    glow = np.zeros_like(bright, dtype=np.float64)
    for sigma in sigmas:
        glow += gaussian_filter(core, sigma=sigma)
    return np.clip(bright + strength * glow, 0.0, 1.0)


# -----------------------------------------------------------------------------
# Colorize
# -----------------------------------------------------------------------------


def colorize(
    bright: FloatArray, count: FloatArray, cmap_name: str = "magma"
) -> Uint8Array:
    """Map a brightness field through a registry colormap to ``(H, W, 4)`` uint8.

    Cells with ``count == 0`` are forced to exact black ``(0, 0, 0, 255)`` so
    the background is crisp rather than the colormap's not-quite-black ``cmap(0)``
    tint. ``cmap_name`` is resolved through
    :func:`chaotic_systems.visualization.colormaps.get`.
    """
    cmap = colormaps.get(cmap_name)
    rgba = cmap(bright)  # (H, W, 4) float in [0, 1]
    rgba8 = (rgba * 255.0 + 0.5).astype(np.uint8)
    rgba8[count == 0] = _BLACK_RGBA
    return rgba8


# -----------------------------------------------------------------------------
# Top-level render
# -----------------------------------------------------------------------------


def render(
    a: float,
    b: float,
    *,
    n_points: int = DEFAULT_N_POINTS,
    n_iter: int = DEFAULT_N_ITER,
    bins: int = DEFAULT_BINS,
    extent: tuple[float, float, float, float] = DEFAULT_EXTENT,
    tone: ToneMode = "eq_hist",
    gamma: float = DEFAULT_GAMMA,
    cmap_name: str = "magma",
    bloom: bool = False,
    count_max: float | None = None,
    map_fn: MapFn = conradi_map,
    use_numba: bool | None = None,
) -> Uint8Array:
    """Render an attractor-density image to ``(bins, bins, 4)`` uint8 RGBA.

    Runs the full pipeline: accumulate an IC-lattice density histogram for
    ``map_fn`` at ``(a, b)``, tone-map it, optionally bloom it, and colorize
    through the colormap registry on a black background.

    Parameters
    ----------
    a, b
        Map parameters (for Conradi, the two phase shifts in ``[0, 2*pi]``).
    n_points, n_iter, bins
        Seeds per lattice axis, iterations per seed, histogram resolution.
    extent
        Render window ``(xmin, xmax, ymin, ymax)``; defaults to the Conradi
        ``[-1, 1]^2`` bounding box.
    tone
        Tone-map mode (see :func:`tone_map`).
    gamma
        Gamma for the ``log`` / ``cbrt`` modes.
    cmap_name
        A colormap name from :func:`colormaps.available`.
    bloom
        If ``True``, apply the multi-scale Gaussian bloom.
    count_max
        Optional fixed accumulation ceiling for the tone map, overriding the
        per-frame maximum. Hold one value constant across an animation loop so
        brightness does not flicker (CSC-005).
    map_fn
        Vectorized map for the NumPy fallback; defaults to the Conradi map.
    use_numba
        Override the numba/NumPy auto-decision.

    Returns
    -------
    numpy.ndarray
        ``(bins, bins, 4)`` ``uint8`` RGBA, top row first.
    """
    count = accumulate(
        a,
        b,
        n_points=n_points,
        n_iter=n_iter,
        bins=bins,
        extent=extent,
        map_fn=map_fn,
        use_numba=use_numba,
    )
    bright = tone_map(count, tone, gamma=gamma, count_max=count_max)
    if bloom:
        bright = apply_bloom(bright)
    return colorize(bright, count, cmap_name=cmap_name)


__all__ = [
    "DEFAULT_BINS",
    "DEFAULT_GAMMA",
    "DEFAULT_N_ITER",
    "DEFAULT_N_POINTS",
    "DEFAULT_EXTENT",
    "IC_EXTENT",
    "VMAX",
    "VMIN",
    "ToneMode",
    "accumulate",
    "apply_bloom",
    "colorize",
    "conradi_map",
    "render",
    "tone_map",
]
