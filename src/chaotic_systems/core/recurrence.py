"""Recurrence plots and Recurrence Quantification Analysis (RQA).

A *recurrence plot* (Eckmann, Kamphorst & Ruelle 1987) of a trajectory
:math:`\\{x_i\\}_{i=1}^N` is the binary matrix

.. math::

    R_{ij} = \\Theta\\bigl(\\varepsilon - \\|x_i - x_j\\|\\bigr),

i.e. 1 when state :math:`x_i` is within :math:`\\varepsilon` of
state :math:`x_j`, else 0. Plotted as a black-and-white image, the
matrix exposes the geometric structure of the orbit in a way the
3D render alone can't:

- **Periodic orbits** appear as a grid of parallel diagonal stripes
  spaced one period apart.
- **Chaotic orbits** show short, broken diagonals and dot clouds —
  Lyapunov-time-bounded recurrences.
- **Drifting / non-stationary** orbits show a fading top-left to
  bottom-right pattern.
- **Laminar phases** (intermittency) appear as vertical / horizontal
  bars.

RQA (Recurrence Quantification Analysis, Webber & Zbilut 1994)
condenses the matrix into scalar measures of how recurrent and
how *deterministic* the orbit is. The standard set this module
ships (Marwan et al. 2007):

- **RR** (Recurrence Rate) — overall density of recurrences.
- **DET** (Determinism) — fraction of recurrence points on
  diagonal lines of length ≥ ``l_min``.
- **LAM** (Laminarity) — fraction on vertical lines of length
  ≥ ``v_min``.
- **L_max** / **V_max** — longest diagonal / vertical line.
- **L_mean** / **TT** — mean diagonal / vertical line length.
- **ENTR** — Shannon entropy of the diagonal-length distribution.

PyRQA (Rawald et al., arXiv 2402.16853, Jan 2024) is the SOTA
OpenCL-accelerated implementation but ships an OpenCL toolchain
dependency we deliberately don't want as a hard requirement. A
~200-line numpy implementation is enough for the
``N ≤ 10000`` trajectories the GUI surfaces — the recurrence
matrix is ``O(N²)`` in both time and space, capped at ~100 MB at
N = 10000 with int8 storage.

References
----------
- J.-P. Eckmann, S. O. Kamphorst, D. Ruelle, *Recurrence Plots of
  Dynamical Systems*, Europhys. Lett. 4 (1987), 973-977 — the
  original construction.
- C. L. Webber Jr. & J. P. Zbilut, *Dynamical assessment of
  physiological systems and states using recurrence plot
  strategies*, J. Appl. Physiol. 76 (1994), 965-973 — RQA
  introduction.
- N. Marwan, M. C. Romano, M. Thiel, J. Kurths, *Recurrence
  plots for the analysis of complex systems*, Phys. Rep. 438
  (2007), 237-329 — the modern canonical reference; every
  formula here matches §3.
- T. Rawald, M. Sips, N. Marwan, *PyRQA — Conducting Recurrence
  Quantification Analysis on very long time series efficiently*,
  arXiv:2402.16853 (Jan 2024) — the OpenCL implementation this
  module reproduces in pure numpy.

See also
--------
- :mod:`chaotic_systems.visualization.recurrence_plot` — matplotlib
  renderer.
- :mod:`chaotic_systems.gui.recurrence_panel` — PySide6 explorer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from chaotic_systems.core.base import FloatArray


@dataclass(frozen=True, slots=True)
class RQAStats:
    """Recurrence Quantification Analysis scalar statistics.

    Every field follows the Marwan et al. (2007) §3 conventions.

    Attributes
    ----------
    rr
        **Recurrence Rate**. Density of recurrence points,
        excluding the line of identity (LOI, ``i = j``) and any
        Theiler-band neighbours (``|i - j| < theiler``).
        ``rr ∈ [0, 1]``.
    det
        **Determinism**. Fraction of recurrence points (in the
        off-diagonal half) that lie on diagonal lines of length
        ``≥ l_min``. High for deterministic systems, low for
        stochastic ones.
    lam
        **Laminarity**. Fraction of recurrence points on vertical
        lines of length ``≥ v_min``. High during *laminar phases*
        of intermittent dynamics.
    l_max
        Longest diagonal line (excluding LOI). ``l_max → N`` is
        characteristic of periodic / quasi-periodic orbits.
    v_max
        Longest vertical line. Long verticals appear in laminar
        / trapping regions.
    l_mean
        Mean diagonal-line length (of lines ``≥ l_min``).
    tt
        **Trapping Time** — mean vertical-line length (of lines
        ``≥ v_min``).
    entr
        Shannon entropy of the diagonal-line-length distribution.
        Periodic orbits give low entropy (lengths concentrate at
        one value); chaotic orbits give higher entropy.
    n
        Trajectory length (``len(trajectory)``).
    l_min
        Diagonal-line threshold used for DET / L_max / L_mean / ENTR.
    v_min
        Vertical-line threshold used for LAM / V_max / TT.
    theiler
        Theiler-window size used (``|i - j| < theiler`` excluded).
    """

    rr: float
    det: float
    lam: float
    l_max: int
    v_max: int
    l_mean: float
    tt: float
    entr: float
    n: int
    l_min: int
    v_min: int
    theiler: int


def recurrence_matrix(
    trajectory: FloatArray | Any,
    *,
    epsilon: float,
    norm: Literal["euclidean", "maximum"] = "euclidean",
    theiler: int = 0,
) -> np.ndarray:
    """Compute the recurrence matrix :math:`R_{ij} = \\Theta(\\varepsilon - \\|x_i - x_j\\|)`.

    Parameters
    ----------
    trajectory
        Either a ``(N, d)`` ndarray of state samples or any object
        exposing a ``.y`` attribute of that shape (e.g. a
        :class:`~chaotic_systems.core.Trajectory`).
    epsilon
        Recurrence threshold. The typical heuristic
        (Marwan et al. 2007 §2.1) is 5-25% of the trajectory's
        bounding-box diagonal: small enough that recurrences carry
        information, large enough to be statistically significant.
    norm
        ``"euclidean"`` (L2; default) or ``"maximum"`` (L∞ /
        Chebyshev). L2 is the canonical choice; L∞ has theoretical
        advantages on strange attractors with measure-theoretic
        analysis.
    theiler
        Theiler window — ``|i - j| < theiler`` entries are forced
        to ``False`` to remove the trivial self-correlation along
        the line of identity. ``theiler = 0`` (default) keeps the
        LOI in the matrix; pass ``theiler = 1`` to mask just the
        diagonal, or a larger value to ignore samples that are
        close in *time* as well as space (useful at small dt).

    Returns
    -------
    ndarray
        Boolean array of shape ``(N, N)``, ``dtype=bool``. Memory
        is ``N²`` bytes — ~100 MB at N = 10000.

    Raises
    ------
    ValueError
        If the trajectory is malformed, ``epsilon <= 0``, or
        ``theiler < 0``.
    """
    arr = _coerce_states(trajectory)
    if float(epsilon) <= 0.0:
        raise ValueError(f"epsilon must be positive (got {epsilon!r})")
    if int(theiler) < 0:
        raise ValueError(f"theiler must be >= 0 (got {theiler!r})")

    # Pairwise distances. For N up to ~5000 the explicit broadcast
    # is fine (memory ~25 MB at N=5000, d=3). For larger N we fall
    # back to a chunked computation that doesn't materialize the
    # full (N, N, d) tensor at once.
    n = arr.shape[0]
    if n * n > 64 * 1024 * 1024:  # > 64M float64s ~ 512 MB
        dist = _pairwise_distances_chunked(arr, norm=norm)
    else:
        dist = _pairwise_distances(arr, norm=norm)

    matrix = dist <= float(epsilon)
    if int(theiler) > 0:
        idx = np.arange(n)
        for k in range(-int(theiler) + 1, int(theiler)):
            mask = np.diag(np.ones(n - abs(k), dtype=bool), k=k)
            matrix[mask] = False
        # Set the main diagonal too if theiler >= 1.
        matrix[idx, idx] = False
    return matrix


def _coerce_states(trajectory: FloatArray | Any) -> np.ndarray:
    """Pull a ``(N, d)`` state array out of a Trajectory or raw ndarray."""
    if isinstance(trajectory, np.ndarray):
        arr = np.ascontiguousarray(trajectory, dtype=np.float64)
    else:
        if not hasattr(trajectory, "y"):
            raise TypeError(
                "recurrence input must have a .y attribute or be an ndarray; "
                f"got {type(trajectory).__name__}"
            )
        arr = np.ascontiguousarray(trajectory.y, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError(
            f"trajectory must be 2-D (N, state_dim); got shape {arr.shape}"
        )
    if arr.shape[0] < 2:
        raise ValueError(
            f"trajectory must have at least 2 samples; got {arr.shape[0]}"
        )
    if not np.isfinite(arr).all():
        raise ValueError("trajectory contains non-finite entries")
    return arr


def _pairwise_distances(
    states: np.ndarray, *, norm: str
) -> np.ndarray:
    """Compute all-pairs distances via NumPy broadcasting. ``O(N² d)``."""
    diffs = states[:, None, :] - states[None, :, :]
    if norm == "euclidean":
        return np.linalg.norm(diffs, axis=2)
    if norm == "maximum":
        return np.max(np.abs(diffs), axis=2)
    raise ValueError(f"unknown norm {norm!r}; choose 'euclidean' or 'maximum'")


def _pairwise_distances_chunked(
    states: np.ndarray,
    *,
    norm: str,
    chunk: int = 1024,
) -> np.ndarray:
    """Row-wise chunked variant for large N — bounds peak memory.

    For N > ~5000 the ``(N, N, d)`` broadcast tensor would push the
    process into hundreds of MB or worse. This computes one row-chunk
    of distances at a time and assembles the (N, N) result.
    """
    n = states.shape[0]
    dist = np.empty((n, n), dtype=np.float64)
    for start in range(0, n, chunk):
        end = min(n, start + chunk)
        diffs = states[start:end, None, :] - states[None, :, :]
        if norm == "euclidean":
            dist[start:end] = np.linalg.norm(diffs, axis=2)
        elif norm == "maximum":
            dist[start:end] = np.max(np.abs(diffs), axis=2)
        else:
            raise ValueError(
                f"unknown norm {norm!r}; choose 'euclidean' or 'maximum'"
            )
    return dist


# --------------------------------------------------------------------------
# RQA scalars.
# --------------------------------------------------------------------------


def rqa(
    matrix: np.ndarray,
    *,
    l_min: int = 2,
    v_min: int = 2,
    theiler: int = 0,
) -> RQAStats:
    """Compute the standard RQA statistics from a recurrence matrix.

    Parameters
    ----------
    matrix
        Boolean ``(N, N)`` recurrence matrix.
    l_min
        Minimum length to count a diagonal as a line (Marwan §3.3,
        canonical default is 2). Lines shorter than this contribute
        to neither DET nor L_max / ENTR.
    v_min
        Minimum length for vertical lines (Marwan §3.4, canonical
        default is 2).
    theiler
        Theiler-window size that was applied when the matrix was
        built. Used here to *describe* the diagram on the returned
        stats; the matrix itself is already masked by the caller.

    Returns
    -------
    RQAStats

    Raises
    ------
    ValueError
        If ``matrix`` is not a square boolean array, or ``l_min`` /
        ``v_min`` are out of range.
    """
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError(
            f"matrix must be square (N, N); got shape {matrix.shape}"
        )
    if int(l_min) < 1:
        raise ValueError(f"l_min must be >= 1 (got {l_min!r})")
    if int(v_min) < 1:
        raise ValueError(f"v_min must be >= 1 (got {v_min!r})")
    matrix_bool = matrix.astype(bool, copy=False)
    n = int(matrix_bool.shape[0])

    # Recurrence Rate: density excluding the main diagonal.
    # Marwan §3.1: RR = (1 / N²) Σ R_ij, but the LOI contributes N
    # trivial recurrences; we subtract them out for a non-trivial RR.
    n_recurrences = int(matrix_bool.sum())
    n_loi = int(np.diag(matrix_bool).sum())
    denom = n * n - n  # excludes LOI
    rr = float(n_recurrences - n_loi) / float(denom) if denom > 0 else 0.0

    # Diagonal lines (excluding the LOI). Walk every off-diagonal k.
    diag_lengths: list[int] = []
    for k in range(-(n - 1), n):
        if k == 0:
            continue
        line = np.diag(matrix_bool, k=k)
        diag_lengths.extend(_run_lengths(line))
    diag_arr = np.asarray(diag_lengths, dtype=np.int64)
    diag_long = diag_arr[diag_arr >= int(l_min)]

    n_on_long_diag = int(diag_long.sum())
    # DET denominator: total recurrences off the LOI. Diagonal symmetry
    # means we count each pair twice; that cancels out in the ratio.
    det = (
        float(n_on_long_diag) / float(n_recurrences - n_loi)
        if (n_recurrences - n_loi) > 0
        else 0.0
    )
    l_max = int(diag_arr.max()) if diag_arr.size else 0
    l_mean = float(diag_long.mean()) if diag_long.size else 0.0

    # Vertical lines (columns). All columns count — verticals include
    # the LOI's row positions, so unlike DET we don't subtract LOI.
    vert_lengths: list[int] = []
    for j in range(n):
        vert_lengths.extend(_run_lengths(matrix_bool[:, j]))
    vert_arr = np.asarray(vert_lengths, dtype=np.int64)
    vert_long = vert_arr[vert_arr >= int(v_min)]
    n_on_long_vert = int(vert_long.sum())
    lam = (
        float(n_on_long_vert) / float(n_recurrences)
        if n_recurrences > 0
        else 0.0
    )
    v_max = int(vert_arr.max()) if vert_arr.size else 0
    tt = float(vert_long.mean()) if vert_long.size else 0.0

    # Entropy of the diagonal-line-length distribution (lengths ≥ l_min).
    # Marwan §3.5: ENTR = -Σ p(l) ln p(l). Higher = more diverse
    # line-length spectrum (chaotic orbits); lower = orbits with one
    # dominant line length (periodic).
    if diag_long.size > 0:
        counts = np.bincount(diag_long)
        probs = counts / counts.sum()
        nz = probs[probs > 0]
        entr = float(-(nz * np.log(nz)).sum())
    else:
        entr = 0.0

    return RQAStats(
        rr=float(rr),
        det=float(det),
        lam=float(lam),
        l_max=int(l_max),
        v_max=int(v_max),
        l_mean=float(l_mean),
        tt=float(tt),
        entr=float(entr),
        n=n,
        l_min=int(l_min),
        v_min=int(v_min),
        theiler=int(theiler),
    )


def _run_lengths(line: np.ndarray) -> list[int]:
    """Return the lengths of every contiguous-True run in a 1-D bool array.

    Vectorized — single ``np.diff`` over the boundary deltas, no
    Python loops over samples. Empty input returns an empty list;
    a line of all ``True`` returns ``[len(line)]``.
    """
    if line.size == 0:
        return []
    arr = line.astype(np.int8, copy=False)
    # Find rising/falling edges by padding with a False on each end
    # then taking the diff. Edges of value +1 are starts; -1 are ends.
    padded = np.concatenate([[0], arr, [0]])
    edges = np.diff(padded)
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)
    return (ends - starts).tolist()


# --------------------------------------------------------------------------
# Convenience: bbox-diagonal heuristic for epsilon.
# --------------------------------------------------------------------------


def suggest_epsilon(
    trajectory: FloatArray | Any,
    *,
    fraction: float = 0.1,
) -> float:
    """Return a sensible default ``epsilon`` for a trajectory.

    The Marwan et al. (2007) §2.1 heuristic is to pick
    ``epsilon ≈ 0.05–0.25 * diam(attractor)`` — large enough that
    the recurrence rate isn't dominated by integrator noise, small
    enough that recurrences carry geometric information. We use
    the bounding-box diagonal as a cheap proxy for the attractor
    diameter; the default ``fraction = 0.1`` (10%) sits in the
    middle of the range and gives recurrence rates ~3-10% on the
    canonical chaotic systems.
    """
    if not 0.0 < float(fraction) <= 1.0:
        raise ValueError(f"fraction must be in (0, 1]; got {fraction!r}")
    states = _coerce_states(trajectory)
    bbox = float(np.linalg.norm(states.max(axis=0) - states.min(axis=0)))
    if bbox == 0.0:
        # Degenerate / constant trajectory — any positive epsilon works.
        # Return a tiny positive default so downstream comparisons stay sane.
        return 1e-12
    return float(fraction) * bbox


__all__ = [
    "RQAStats",
    "recurrence_matrix",
    "rqa",
    "suggest_epsilon",
]
