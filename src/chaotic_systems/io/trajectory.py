"""Trajectory file IO — CSV (universal) and NPZ (lossless binary).

V4 from ``docs/proposals/capability-roadmap-2026-05-17.md``. Two
complementary file formats with non-overlapping use cases:

- **CSV** — every spreadsheet, Mathematica, R, MATLAB, and pandas
  workflow consumes CSV out of the box. The format here is the
  obvious one: a single header row ``"t,y0,y1,...,y{state_dim-1}"``
  followed by one row per integrator sample. Floating-point text
  encoding uses NumPy's default ``%.18e`` so the round-trip is
  bit-identical (well, within the float64 → ASCII → float64 spec).
- **NPZ** — NumPy's compressed-binary archive. Stores ``t`` and
  ``y`` as bare arrays, plus three sidecar 0-D string arrays
  (``system``, ``integrator``, ``params_json``) so the metadata
  round-trips losslessly. Picks up gzip-class compression for
  free, so a 4000-sample (N, 4) trajectory typically lands at
  ~40 KB.

The two writers are pure :mod:`numpy` / :mod:`json` — no pandas or
HDF5 dependency.

Both formats round-trip through this module's ``read_*`` helpers
to a flat ``dict`` (CSV) or a richer dict-with-metadata (NPZ).
Callers that want a :class:`~chaotic_systems.core.Trajectory`
back can hand the ``t`` and ``y`` arrays to the constructor:

.. code-block:: python

    from chaotic_systems.core import Trajectory
    from chaotic_systems.io import read_npz

    blob = read_npz("lorenz_run.npz")
    traj = Trajectory(
        t=blob["t"],
        y=blob["y"],
        system=blob["system"],
        integrator=blob["integrator"],
        params=blob["params"],
    )

References
----------
- Convention; every comparable tool (DynamicalSystems.jl,
  pynamical, pynamicalsys) ships CSV + binary trajectory dump
  with similar header shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from chaotic_systems.core.base import FloatArray, Trajectory


def _resolve_trajectory(trajectory: Trajectory | Any) -> Trajectory:
    """Best-effort coercion to a Trajectory-shaped object.

    Accepts either an actual :class:`Trajectory` or anything
    exposing ``.t`` and ``.y``. Validates the shapes the writers
    rely on (``t`` 1-D, ``y`` 2-D, matching N).
    """
    if not hasattr(trajectory, "t") or not hasattr(trajectory, "y"):
        raise TypeError(
            "trajectory IO needs an object with .t and .y attributes; "
            f"got {type(trajectory).__name__}"
        )
    ts = np.ascontiguousarray(trajectory.t, dtype=np.float64)
    ys = np.ascontiguousarray(trajectory.y, dtype=np.float64)
    if ts.ndim != 1:
        raise ValueError(f"trajectory.t must be 1-D; got shape {ts.shape}")
    if ys.ndim != 2:
        raise ValueError(
            f"trajectory.y must be 2-D (N, state_dim); got shape {ys.shape}"
        )
    if ts.shape[0] != ys.shape[0]:
        raise ValueError(
            f"trajectory.t length {ts.shape[0]} != y rows {ys.shape[0]}"
        )
    # If the input is already a Trajectory, return it as-is (preserves
    # metadata); otherwise wrap into a minimal one so the rest of the
    # writer code can read uniform attributes.
    if isinstance(trajectory, Trajectory):
        return trajectory
    return Trajectory(
        t=ts,
        y=ys,
        system=str(getattr(trajectory, "system", "") or ""),
        params=dict(getattr(trajectory, "params", {}) or {}),
        integrator=str(getattr(trajectory, "integrator", "") or ""),
    )


def write_csv(trajectory: Trajectory | Any, path: str | Path) -> Path:
    """Write a trajectory to a CSV file.

    The output has one header row ``"t,y0,y1,...,y{state_dim-1}"``
    followed by ``N`` data rows. Floating-point precision uses NumPy's
    ``%.18e`` so the textual round-trip is float64-faithful.

    Per-system metadata (system name, integrator name, parameter
    values) is NOT in the CSV — CSV is the lowest-common-denominator
    format. Use :func:`write_npz` or :func:`~chaotic_systems.io.run_history.write_json`
    if you want the metadata to round-trip too.

    Parameters
    ----------
    trajectory
        A :class:`Trajectory` or any object with ``.t`` (shape
        ``(N,)``) and ``.y`` (shape ``(N, state_dim)``).
    path
        Destination file path. ``.csv`` extension is conventional but
        not required.

    Returns
    -------
    Path
        The written path, resolved to absolute form.
    """
    traj = _resolve_trajectory(trajectory)
    dest = Path(path).expanduser().resolve()
    n, d = int(traj.y.shape[0]), int(traj.y.shape[1])
    header = "t," + ",".join(f"y{i}" for i in range(d))
    # Stack t as the leftmost column. Avoid Pandas — pure numpy keeps
    # the IO module's dependency footprint at zero.
    arr = np.empty((n, d + 1), dtype=np.float64)
    arr[:, 0] = traj.t
    arr[:, 1:] = traj.y
    np.savetxt(dest, arr, delimiter=",", header=header, comments="", fmt="%.18e")
    return dest


def read_csv(path: str | Path) -> dict[str, FloatArray]:
    """Read a CSV trajectory written by :func:`write_csv`.

    Returns ``{"t": (N,), "y": (N, state_dim)}`` as float64 ndarrays.
    The header row is consumed; metadata is not present in the file
    format (use :func:`read_npz` or
    :func:`~chaotic_systems.io.run_history.read_json` for that).

    Raises
    ------
    FileNotFoundError
        If ``path`` doesn't exist.
    ValueError
        If the file's column count is inconsistent or it has fewer
        than 2 data rows.
    """
    src = Path(path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"no such trajectory CSV: {src}")
    arr = np.loadtxt(src, delimiter=",", skiprows=1, dtype=np.float64)
    if arr.ndim == 1:
        # Single-column CSV — degenerate, would mean state_dim = 0;
        # we don't support it.
        raise ValueError(
            f"trajectory CSV has only 1 column at {src}; expected "
            "at least 2 (t + at least one y component)"
        )
    if arr.shape[0] < 2:
        raise ValueError(
            f"trajectory CSV has only {arr.shape[0]} row(s) at {src}; "
            "expected >= 2"
        )
    ts = np.ascontiguousarray(arr[:, 0], dtype=np.float64)
    ys = np.ascontiguousarray(arr[:, 1:], dtype=np.float64)
    return {"t": ts, "y": ys}


def write_npz(trajectory: Trajectory | Any, path: str | Path) -> Path:
    """Write a trajectory + its metadata to a compressed NPZ archive.

    Stores five entries:

    - ``t`` — shape ``(N,)`` float64.
    - ``y`` — shape ``(N, state_dim)`` float64.
    - ``system`` — 0-D string array carrying the system name.
    - ``integrator`` — 0-D string array carrying the integrator name.
    - ``params_json`` — 0-D string array carrying ``json.dumps(traj.params)``.

    Compression is the NumPy default (zip + DEFLATE). On a 4000-sample
    Lorenz trajectory the file is ~40 KB.

    Returns
    -------
    Path
        The written path, resolved to absolute form.
    """
    traj = _resolve_trajectory(trajectory)
    dest = Path(path).expanduser().resolve()
    # 0-D string arrays are how np.savez round-trips Python str — bare
    # strings would be cast to ndarrays of dtype object, which np.load
    # then refuses with allow_pickle=False.
    params_serialized = json.dumps(
        {str(k): float(v) for k, v in (traj.params or {}).items()},
        sort_keys=True,
    )
    np.savez_compressed(
        dest,
        t=traj.t,
        y=traj.y,
        system=np.asarray(str(traj.system or ""), dtype=str),
        integrator=np.asarray(str(traj.integrator or ""), dtype=str),
        params_json=np.asarray(params_serialized, dtype=str),
    )
    return dest


def read_npz(path: str | Path) -> dict[str, Any]:
    """Read a trajectory NPZ written by :func:`write_npz`.

    Returns a dict with keys ``t``, ``y``, ``system``, ``integrator``,
    ``params``. ``params`` is parsed back from the embedded JSON
    string to a ``dict[str, float]``.

    Raises
    ------
    FileNotFoundError
        If ``path`` doesn't exist.
    KeyError
        If a required entry is missing from the archive.
    """
    src = Path(path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"no such trajectory NPZ: {src}")
    # ``allow_pickle=False`` keeps us off the unsafe NumPy code path
    # (zero need — every stored entry is either a numeric array or a
    # 0-D unicode-string array).
    with np.load(src, allow_pickle=False) as data:
        for required in ("t", "y", "system", "integrator", "params_json"):
            if required not in data.files:
                raise KeyError(
                    f"trajectory NPZ {src} is missing required entry "
                    f"{required!r} (found: {sorted(data.files)})"
                )
        ts = np.ascontiguousarray(data["t"], dtype=np.float64)
        ys = np.ascontiguousarray(data["y"], dtype=np.float64)
        system = str(data["system"])
        integrator = str(data["integrator"])
        params_json = str(data["params_json"])
    try:
        params: dict[str, float] = {
            str(k): float(v) for k, v in json.loads(params_json).items()
        }
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError(
            f"trajectory NPZ {src}: params_json failed to parse: {exc}"
        ) from exc
    return {
        "t": ts,
        "y": ys,
        "system": system,
        "integrator": integrator,
        "params": params,
    }


__all__ = ["read_csv", "read_npz", "write_csv", "write_npz"]
