"""File-format I/O for trajectories and run manifests (V4).

Three small modules:

- :mod:`chaotic_systems.io.trajectory` — write / read a
  :class:`~chaotic_systems.core.Trajectory` to ``.csv`` or
  ``.npz``. CSV is the universal interchange format for spreadsheet
  / Pandas / Mathematica round-trips; NPZ is the lossless
  compressed-binary form that preserves metadata (system, integrator,
  parameter dict) and is the recommended save format for "I want this
  exact run back later."

- :mod:`chaotic_systems.io.run_history` — :class:`RunManifest`
  dataclass + JSON read/write. One per simulation run, captures
  system / params / integrator / dt / t_span / output-file paths
  + a UTC ISO-8601 timestamp + a schema-version field for
  forward-compatibility.

- :mod:`chaotic_systems.visualization.snapshot` (companion module) —
  :func:`~chaotic_systems.visualization.snapshot.save_viewport_png`
  writes the current PyVista renderer's viewport to a PNG file.

This is V4 from ``docs/proposals/capability-roadmap-2026-05-17.md``:
the workflow-completeness commit. The GUI's Export submenu is the
discoverability surface; library callers get the same functions
directly.
"""

from __future__ import annotations

from chaotic_systems.io.run_history import (
    RunManifest,
    manifest_from_trajectory,
    read_json,
    write_json,
)
from chaotic_systems.io.trajectory import (
    read_csv,
    read_npz,
    write_csv,
    write_npz,
)

__all__ = [
    "RunManifest",
    "manifest_from_trajectory",
    "read_csv",
    "read_json",
    "read_npz",
    "write_csv",
    "write_json",
    "write_npz",
]
