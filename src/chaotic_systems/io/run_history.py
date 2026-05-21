"""Per-run JSON manifest (V4).

A :class:`RunManifest` is a one-file summary of a single simulation
run: which system, which parameter values, which integrator, which
``dt`` / ``t_span``, plus the file paths the user chose to save the
trajectory / snapshot / video to, plus a UTC ISO-8601 timestamp.

The use case the proposal calls out (V4 §Rationale): "I want to put
this trajectory in a paper." After exporting CSV / NPZ / PNG / MP4
from a Run, write out the manifest too — six months later you can
reopen the manifest and know exactly which parameters produced the
data.

The format is plain JSON with a ``schema_version`` field so we can
evolve the layout without breaking existing manifests. v1 ships
:data:`SCHEMA_VERSION = 1`.

References
----------
- Convention; the same pattern as MLflow's ``meta.yaml`` or
  Weights & Biases' ``wandb-metadata.json``, scaled to a single
  scientific simulation run.
"""

from __future__ import annotations

import importlib.metadata
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Bump this any time the manifest layout changes incompatibly.
#: v1 is what's documented in this module; the readers handle older
#: versions by raising a clear error rather than silently misparsing.
SCHEMA_VERSION: int = 1


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with a 'Z' suffix."""
    return (
        datetime.now(tz=UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _package_version() -> str:
    """Return the installed chaotic-systems-dynamics version string, or "unknown"."""
    try:
        return importlib.metadata.version("chaotic-systems-dynamics")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover - dev env
        return "unknown"


@dataclass(frozen=True, slots=True)
class RunManifest:
    """Per-run metadata captured at export time.

    Attributes
    ----------
    system
        Name of the dynamical system that produced the run (e.g.
        ``"Lorenz"`` / ``"MackeyGlass"`` / ``"Kuramoto"``).
    params
        Parameter values as the run actually used them (the system's
        default params merged with any user overrides). Floats only —
        non-numeric keys are flattened to ``str`` to stay JSON-safe.
    integrator
        Integrator name as it appeared on the Trajectory
        (``"RK45"`` / ``"yoshida4"`` / ``"BellenRK4"`` / ...).
    dt
        Step size, if the user supplied one. ``None`` when the
        integrator was driven by an ``n_points`` request alone.
    t_span
        ``(t0, t1)`` interval as a 2-tuple.
    n_points
        Number of recorded samples in the trajectory (post-resample).
    outputs
        Map of file-type → absolute path. Only the formats the
        user actually exported are included; e.g.
        ``{"csv": "/Users/.../lorenz.csv", "png": "/Users/.../lorenz.png"}``.
    state_dim
        Echoed from the system for convenience.
    created_at
        UTC ISO-8601 timestamp at manifest construction.
    schema_version
        See module-level :data:`SCHEMA_VERSION`.
    package_version
        Installed ``chaotic-systems-dynamics`` distribution version
        (``"unknown"`` outside an installed environment).
    """

    system: str
    params: dict[str, float]
    integrator: str
    dt: float | None
    t_span: tuple[float, float]
    n_points: int
    outputs: dict[str, str] = field(default_factory=dict)
    state_dim: int = 0
    created_at: str = field(default_factory=_utc_now_iso)
    schema_version: int = SCHEMA_VERSION
    package_version: str = field(default_factory=_package_version)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict mirror of this manifest."""
        d = asdict(self)
        # Normalize tuple-valued t_span to a JSON list explicitly.
        d["t_span"] = list(self.t_span)
        return d


def manifest_from_trajectory(
    trajectory: Any,
    *,
    dt: float | None = None,
    outputs: Mapping[str, str | Path] | None = None,
) -> RunManifest:
    """Build a :class:`RunManifest` from a Trajectory + optional output paths.

    Pulls ``system`` / ``params`` / ``integrator`` from the trajectory
    object (these are all set by every system's ``.simulate(...)``
    path) and infers ``t_span`` / ``n_points`` / ``state_dim`` from
    the ``.t`` / ``.y`` arrays.

    Parameters
    ----------
    trajectory
        Any object exposing ``.t`` / ``.y`` / ``.system`` / ``.params`` /
        ``.integrator`` (the :class:`~chaotic_systems.core.Trajectory`
        contract).
    dt
        Caller-supplied step size, if known. Stored verbatim;
        ``None`` is fine.
    outputs
        Optional mapping of output-file-kind to path
        (e.g. ``{"csv": "/.../lorenz.csv"}``). Paths are normalized
        to absolute strings via :meth:`pathlib.Path.expanduser`/
        :meth:`pathlib.Path.resolve`.

    Returns
    -------
    RunManifest
    """
    import numpy as np

    if not hasattr(trajectory, "t") or not hasattr(trajectory, "y"):
        raise TypeError(
            "manifest_from_trajectory needs an object with .t / .y; got "
            f"{type(trajectory).__name__}"
        )
    ts = np.ascontiguousarray(trajectory.t, dtype=np.float64)
    ys = np.ascontiguousarray(trajectory.y, dtype=np.float64)
    if ts.ndim != 1 or ts.shape[0] < 2:
        raise ValueError(
            f"trajectory.t must be 1-D with >= 2 samples; got shape {ts.shape}"
        )
    if ys.ndim != 2 or ys.shape[0] != ts.shape[0]:
        raise ValueError(
            f"trajectory.y must be (N, state_dim) with matching N; "
            f"got shape {ys.shape}"
        )
    params_raw = getattr(trajectory, "params", {}) or {}
    params_clean: dict[str, float] = {
        str(k): float(v) for k, v in params_raw.items()
    }
    outputs_clean: dict[str, str] = {}
    if outputs:
        for kind, p in outputs.items():
            outputs_clean[str(kind)] = str(Path(p).expanduser().resolve())
    return RunManifest(
        system=str(getattr(trajectory, "system", "") or ""),
        params=params_clean,
        integrator=str(getattr(trajectory, "integrator", "") or ""),
        dt=float(dt) if dt is not None else None,
        t_span=(float(ts[0]), float(ts[-1])),
        n_points=int(ts.shape[0]),
        outputs=outputs_clean,
        state_dim=int(ys.shape[1]),
    )


def write_json(manifest: RunManifest, path: str | Path) -> Path:
    """Write a :class:`RunManifest` to a JSON file.

    The output is pretty-printed with 2-space indent for human
    diff-friendliness; keys are sorted so the manifest is
    deterministic across runs.

    Returns
    -------
    Path
        Absolute path to the written file.
    """
    if not isinstance(manifest, RunManifest):
        raise TypeError(
            f"write_json expected a RunManifest; got {type(manifest).__name__}"
        )
    dest = Path(path).expanduser().resolve()
    with dest.open("w", encoding="utf-8") as fh:
        json.dump(manifest.to_dict(), fh, indent=2, sort_keys=True)
        fh.write("\n")
    return dest


def read_json(path: str | Path) -> RunManifest:
    """Read a JSON file written by :func:`write_json` back to a :class:`RunManifest`.

    The schema-version check is strict by design — a manifest written
    by a future version of the project should not silently lose
    fields when read by an older version. Bump :data:`SCHEMA_VERSION`
    when changing the layout and add a migration here if needed.

    Raises
    ------
    FileNotFoundError
        If ``path`` doesn't exist.
    ValueError
        If the JSON is malformed, a required key is missing, or
        ``schema_version`` is newer than this module supports.
    """
    src = Path(path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"no such run manifest: {src}")
    with src.open("r", encoding="utf-8") as fh:
        try:
            raw = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"run manifest {src} is not valid JSON: {exc}"
            ) from exc
    if not isinstance(raw, dict):
        raise ValueError(
            f"run manifest {src} top-level must be an object; got {type(raw).__name__}"
        )
    version = int(raw.get("schema_version", 0))
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"run manifest {src} schema_version={version} is newer than "
            f"this build supports ({SCHEMA_VERSION}); upgrade "
            "chaotic-systems-dynamics to read it."
        )
    required = (
        "system",
        "params",
        "integrator",
        "t_span",
        "n_points",
        "schema_version",
    )
    for key in required:
        if key not in raw:
            raise ValueError(
                f"run manifest {src} is missing required key {key!r}"
            )
    t_span_raw = raw["t_span"]
    if not (isinstance(t_span_raw, list) and len(t_span_raw) == 2):
        raise ValueError(
            f"run manifest {src} t_span must be a 2-element list; "
            f"got {t_span_raw!r}"
        )
    return RunManifest(
        system=str(raw["system"]),
        params={str(k): float(v) for k, v in dict(raw["params"]).items()},
        integrator=str(raw["integrator"]),
        dt=(None if raw.get("dt") is None else float(raw["dt"])),
        t_span=(float(t_span_raw[0]), float(t_span_raw[1])),
        n_points=int(raw["n_points"]),
        outputs={str(k): str(v) for k, v in dict(raw.get("outputs", {})).items()},
        state_dim=int(raw.get("state_dim", 0)),
        created_at=str(raw.get("created_at", _utc_now_iso())),
        schema_version=version,
        package_version=str(raw.get("package_version", "unknown")),
    )


__all__ = [
    "SCHEMA_VERSION",
    "RunManifest",
    "manifest_from_trajectory",
    "read_json",
    "write_json",
]
