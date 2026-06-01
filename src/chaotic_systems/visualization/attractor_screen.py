r"""Lyapunov screening of the Conradi map's ``(a, b)`` parameter plane (CSC-004).

Computes the largest Lyapunov exponent on a grid over ``(a, b) in [0, 2*pi]^2``
so the panel can show a "where is it dynamically rich" backdrop for the
parameter-path editor (CSC-005) — Sprott-style aesthetic screening of an
attractor family.

This is the **vectorized** form of the discrete-map Benettin estimator in
:func:`chaotic_systems.core.lyapunov.largest_lyapunov_discrete` (CSC-003): a
single tangent vector is iterated for *every* grid cell at once as NumPy arrays
of shape ``(grid, grid)``, accumulating the average log-stretch. A 1x1 grid
reproduces the scalar estimator (asserted in the tests). Alongside the exponent
field it tracks the orbit's spatial spread so a **degeneracy guard** can reject
collapsed point attractors (a near-zero-spread orbit is a fixed point, not an
attractor worth rendering).

.. important::

   High Lyapunov exponent does **not** mean "looks like Conradi's art". As
   recorded in ``CONTEXT.md`` (CSC-003), Conradi's canonical art parameters
   ``(5.46, 4.55)`` and ``(1.7, 2.3)`` are **periodic** (largest exponent
   ``<= 0``) — the density art is the *transient flow* of the seed lattice, not
   a chaotic attractor. So this screening is an informational overlay, not a
   constraint: the visually interesting (periodic) regions must NOT be excluded.

References
----------
- J. C. Sprott (1993), *Automatic generation of strange attractors*,
  Computers & Graphics 17(3):325-332, DOI 10.1016/0097-8493(93)90082-K (the
  Lyapunov-exponent + spatial-extent aesthetic screening of an attractor
  family; reject collapsed / unbounded orbits, keep the bounded chaotic ones).
- G. Benettin, L. Galgani, A. Giorgilli, J.-M. Strelcyn (1980),
  *Lyapunov Characteristic Exponents...*, Meccanica 15:9-30,
  DOI 10.1007/BF02128236 (the tangent-map renormalization estimator).
"""

from __future__ import annotations

import math

import numpy as np

from chaotic_systems.core.base import FloatArray

# Screening window: the Conradi phase shifts a, b are angles spanning [0, 2*pi]
# (the parameter-space inset in Conradi's animations spans exactly this square).
SCREEN_A_RANGE: tuple[float, float] = (0.0, 2.0 * math.pi)
SCREEN_B_RANGE: tuple[float, float] = (0.0, 2.0 * math.pi)

#: Grid resolution per axis for the screening sweep (grid x grid cells).
DEFAULT_GRID: int = 96
#: Accumulation iterations per cell (after the transient). Shorter than a
#: precise single-point estimate; enough to fix the sign of the exponent.
DEFAULT_N: int = 600
#: Transient iterations discarded before accumulation.
DEFAULT_N_TRANSIENT: int = 200
#: Generic interior seed (the Conradi map self-bounds to [-1, 1]^2).
DEFAULT_SEED_STATE: tuple[float, float] = (0.1, 0.1)
#: Direction seed for the initial tangent (reproducibility; the leading
#: exponent is direction-independent generically).
_TANGENT_SEED: int = 0x5C12EE

#: Below this RMS spatial spread the orbit has collapsed (or is collapsing) to
#: a (near-)fixed point — a degenerate attractor. Set at 1e-2: a settling
#: fixed point reads ~1e-3 at the short screening budget, while a genuine
#: periodic cycle or chaotic attractor visits a spread-out set (spread >~ 0.1
#: for cycles, ~0.5 for the Conradi chaotic regime), so 1e-2 cleanly separates
#: "collapsed to a point" from a real attractor.
SPREAD_FLOOR: float = 1e-2
#: Largest-exponent threshold above which a cell is flagged "chaotic".
DEFAULT_LLE_THRESHOLD: float = 0.0


def lyapunov_grid(
    grid: int = DEFAULT_GRID,
    *,
    n: int = DEFAULT_N,
    n_transient: int = DEFAULT_N_TRANSIENT,
    a_range: tuple[float, float] = SCREEN_A_RANGE,
    b_range: tuple[float, float] = SCREEN_B_RANGE,
    seed_state: tuple[float, float] = DEFAULT_SEED_STATE,
) -> tuple[FloatArray, FloatArray]:
    """Largest Lyapunov exponent + orbit spread over the ``(a, b)`` grid.

    Vectorized Benettin renormalization (the batched form of CSC-003's
    :func:`~chaotic_systems.core.lyapunov.largest_lyapunov_discrete`) for the
    Conradi map ``x' = sin(x^2 - y^2 + a)``, ``y' = cos(2xy + b)`` evaluated at
    every cell of a ``grid x grid`` lattice of ``(a, b)`` values.

    Parameters
    ----------
    grid
        Cells per axis.
    n
        Accumulation iterations per cell.
    n_transient
        Transient iterations discarded first.
    a_range, b_range
        Parameter ranges (defaults to ``[0, 2*pi]`` each).
    seed_state
        Initial ``(x, y)`` for every cell.

    Returns
    -------
    lle : numpy.ndarray
        ``(grid, grid)`` array of largest Lyapunov exponents. Row index runs
        over ``b`` (``b_range`` linspace), column index over ``a``.
    spread : numpy.ndarray
        ``(grid, grid)`` RMS spatial extent of each orbit over the accumulation
        window — near zero for a collapsed point attractor.
    """
    if grid < 1:
        raise ValueError(f"grid must be >= 1, got {grid}")
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")

    a_lin = np.linspace(a_range[0], a_range[1], grid)
    b_lin = np.linspace(b_range[0], b_range[1], grid)
    grid_a, grid_b = np.meshgrid(a_lin, b_lin)  # (grid, grid); row=b, col=a

    x = np.full(grid_a.shape, seed_state[0], dtype=np.float64)
    y = np.full(grid_a.shape, seed_state[1], dtype=np.float64)

    # Burn off the transient.
    for _ in range(n_transient):
        x, y = np.sin(x * x - y * y + grid_a), np.cos(2.0 * x * y + grid_b)

    rng = np.random.default_rng(_TANGENT_SEED)
    vx = rng.standard_normal(grid_a.shape)
    vy = rng.standard_normal(grid_a.shape)
    norm = np.hypot(vx, vy)
    vx /= norm
    vy /= norm

    log_sum = np.zeros(grid_a.shape, dtype=np.float64)
    # Running sums for the spread (std) of (x, y) over the window.
    sum_x = np.zeros(grid_a.shape, dtype=np.float64)
    sum_xx = np.zeros(grid_a.shape, dtype=np.float64)
    sum_y = np.zeros(grid_a.shape, dtype=np.float64)
    sum_yy = np.zeros(grid_a.shape, dtype=np.float64)

    for _ in range(n):
        u = x * x - y * y + grid_a
        v = 2.0 * x * y + grid_b
        cos_u = np.cos(u)
        sin_v = np.sin(v)
        # J = [[2x cos u, -2y cos u], [-2y sin v, -2x sin v]]; push the tangent.
        new_vx = 2.0 * x * cos_u * vx - 2.0 * y * cos_u * vy
        new_vy = -2.0 * y * sin_v * vx - 2.0 * x * sin_v * vy
        r = np.hypot(new_vx, new_vy)
        r_safe = np.where(r > 0.0, r, 1.0)
        log_sum += np.log(r_safe)
        vx = new_vx / r_safe
        vy = new_vy / r_safe
        # Advance the base point (x' = sin(u), y' = cos(v)).
        x = np.sin(u)
        y = np.cos(v)
        sum_x += x
        sum_xx += x * x
        sum_y += y
        sum_yy += y * y

    lle = log_sum / n
    mean_x = sum_x / n
    mean_y = sum_y / n
    var_x = np.clip(sum_xx / n - mean_x * mean_x, 0.0, None)
    var_y = np.clip(sum_yy / n - mean_y * mean_y, 0.0, None)
    spread = np.sqrt(var_x + var_y)
    return lle, spread


def interesting_mask(
    lle: FloatArray,
    spread: FloatArray,
    *,
    lle_threshold: float = DEFAULT_LLE_THRESHOLD,
    spread_floor: float = SPREAD_FLOOR,
) -> FloatArray:
    """Boolean mask of cells that are chaotic *and* non-degenerate.

    ``True`` where the largest exponent exceeds ``lle_threshold`` (chaotic) and
    the orbit spread exceeds ``spread_floor`` (not a collapsed point attractor)
    — Sprott's aesthetic-screening criterion. Note (see the module docstring)
    that this flags *chaos*, which is distinct from "produces Conradi's art":
    the canonical art parameters are periodic and would read ``False`` here.
    """
    return (lle > lle_threshold) & (spread > spread_floor)


__all__ = [
    "DEFAULT_GRID",
    "DEFAULT_LLE_THRESHOLD",
    "DEFAULT_N",
    "DEFAULT_N_TRANSIENT",
    "SCREEN_A_RANGE",
    "SCREEN_B_RANGE",
    "SPREAD_FLOOR",
    "interesting_mask",
    "lyapunov_grid",
]
