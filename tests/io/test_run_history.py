"""Per-run JSON manifest tests (V4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chaotic_systems.io import (
    RunManifest,
    manifest_from_trajectory,
    read_json,
    write_json,
)
from chaotic_systems.io.run_history import SCHEMA_VERSION
from chaotic_systems.systems import Lorenz


def _make_traj():
    return Lorenz().simulate((0.0, 5.0), n_points=100, integrator="RK45")


# --- Builder ----------------------------------------------------------


def test_manifest_from_trajectory_captures_canonical_fields() -> None:
    traj = _make_traj()
    m = manifest_from_trajectory(traj, dt=0.05)
    assert m.system == "Lorenz"
    assert m.integrator == "RK45"
    assert m.params["sigma"] == pytest.approx(10.0)
    assert m.t_span == (pytest.approx(0.0), pytest.approx(5.0))
    assert m.n_points == 100
    assert m.dt == pytest.approx(0.05)
    assert m.state_dim == 3
    assert m.schema_version == SCHEMA_VERSION
    assert m.created_at.endswith("Z")
    assert m.package_version  # may be "unknown" in dev, but never empty


def test_manifest_outputs_resolve_to_absolute_paths(tmp_path: Path) -> None:
    traj = _make_traj()
    rel_csv = tmp_path / "x.csv"
    m = manifest_from_trajectory(traj, outputs={"csv": str(rel_csv)})
    assert Path(m.outputs["csv"]).is_absolute()


def test_manifest_rejects_input_without_t_and_y() -> None:
    class _Nope:
        pass

    with pytest.raises(TypeError, match=".t / .y"):
        manifest_from_trajectory(_Nope())


# --- JSON round-trip --------------------------------------------------


def test_json_round_trip_preserves_every_field(tmp_path: Path) -> None:
    traj = _make_traj()
    m = manifest_from_trajectory(
        traj, dt=0.05, outputs={"csv": tmp_path / "x.csv"}
    )
    dest = write_json(m, tmp_path / "run.json")
    assert dest.exists()
    out = read_json(dest)
    assert out.system == m.system
    assert out.params == m.params
    assert out.integrator == m.integrator
    assert out.dt == pytest.approx(m.dt)
    assert out.t_span == m.t_span
    assert out.n_points == m.n_points
    assert out.outputs == m.outputs
    assert out.state_dim == m.state_dim
    assert out.created_at == m.created_at
    assert out.schema_version == m.schema_version


def test_json_pretty_printed_with_sorted_keys(tmp_path: Path) -> None:
    """The on-disk JSON is human-diff-friendly: indent=2, sort_keys=True."""
    traj = _make_traj()
    m = manifest_from_trajectory(traj)
    dest = write_json(m, tmp_path / "run.json")
    text = dest.read_text()
    # Sorted: ``created_at`` comes before ``dt`` (lexicographic).
    assert text.index('"created_at"') < text.index('"dt"')
    # Indented: at least one line has the 2-space prefix.
    assert any(line.startswith("  ") for line in text.splitlines())


def test_json_accepts_string_path(tmp_path: Path) -> None:
    traj = _make_traj()
    m = manifest_from_trajectory(traj)
    dest = write_json(m, str(tmp_path / "run.json"))
    out = read_json(str(dest))
    assert out.system == "Lorenz"


def test_json_write_rejects_non_manifest_input(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="RunManifest"):
        write_json({"system": "fake"}, tmp_path / "bad.json")  # type: ignore[arg-type]


def test_json_read_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="run manifest"):
        read_json(tmp_path / "does-not-exist.json")


def test_json_read_raises_on_malformed_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("this is not JSON {")
    with pytest.raises(ValueError, match="not valid JSON"):
        read_json(bad)


def test_json_read_raises_on_missing_required_key(tmp_path: Path) -> None:
    bad = tmp_path / "missing.json"
    bad.write_text(json.dumps({"schema_version": 1, "system": "X"}))
    with pytest.raises(ValueError, match="missing required key"):
        read_json(bad)


def test_json_read_raises_on_future_schema_version(tmp_path: Path) -> None:
    """A manifest from a future build must fail loudly, not silently."""
    bad = tmp_path / "future.json"
    payload = {
        "system": "Lorenz",
        "params": {"sigma": 10.0},
        "integrator": "RK45",
        "dt": 0.05,
        "t_span": [0.0, 5.0],
        "n_points": 100,
        "outputs": {},
        "state_dim": 3,
        "created_at": "2099-01-01T00:00:00Z",
        "schema_version": SCHEMA_VERSION + 5,
        "package_version": "1.0.0",
    }
    bad.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="newer than"):
        read_json(bad)


def test_json_read_rejects_non_object_top_level(tmp_path: Path) -> None:
    bad = tmp_path / "list.json"
    bad.write_text(json.dumps([1, 2, 3]))
    with pytest.raises(ValueError, match="must be an object"):
        read_json(bad)


def test_json_read_rejects_bad_t_span_shape(tmp_path: Path) -> None:
    bad = tmp_path / "tspan.json"
    payload = {
        "system": "Lorenz",
        "params": {},
        "integrator": "RK45",
        "dt": None,
        "t_span": [0.0, 1.0, 2.0],  # 3 elements, not 2
        "n_points": 100,
        "schema_version": SCHEMA_VERSION,
    }
    bad.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="2-element list"):
        read_json(bad)


def test_manifest_dataclass_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    m = RunManifest(
        system="X",
        params={},
        integrator="Y",
        dt=None,
        t_span=(0.0, 1.0),
        n_points=2,
    )
    with pytest.raises(FrozenInstanceError):
        m.system = "Z"  # type: ignore[misc]
