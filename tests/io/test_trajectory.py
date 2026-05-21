"""Trajectory IO round-trip tests (V4 — CSV + NPZ)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chaotic_systems.core import Trajectory
from chaotic_systems.io import read_csv, read_npz, write_csv, write_npz
from chaotic_systems.systems import Lorenz


def _make_traj(n: int = 100) -> Trajectory:
    """Lorenz canonical IC, RK45, n_points samples — deterministic across runs."""
    return Lorenz().simulate((0.0, 5.0), n_points=n, integrator="RK45")


# --- CSV --------------------------------------------------------------


def test_csv_round_trip_preserves_t_and_y(tmp_path: Path) -> None:
    traj = _make_traj()
    dest = write_csv(traj, tmp_path / "lorenz.csv")
    assert dest.exists()
    assert dest.stat().st_size > 0
    out = read_csv(dest)
    np.testing.assert_array_equal(out["t"], traj.t)
    np.testing.assert_array_equal(out["y"], traj.y)


def test_csv_header_is_t_y0_y1_yN(tmp_path: Path) -> None:
    traj = _make_traj()
    dest = write_csv(traj, tmp_path / "lorenz.csv")
    first_line = dest.read_text().splitlines()[0]
    assert first_line == "t,y0,y1,y2"


def test_csv_round_trip_via_string_path(tmp_path: Path) -> None:
    """Accept ``str`` for ``path`` (the QFileDialog returns ``str``)."""
    traj = _make_traj(50)
    dest = write_csv(traj, str(tmp_path / "x.csv"))
    out = read_csv(str(dest))
    np.testing.assert_array_equal(out["y"], traj.y)


def test_csv_accepts_duck_typed_trajectory(tmp_path: Path) -> None:
    """Anything with ``.t`` and ``.y`` round-trips through CSV."""

    class _Stub:
        t = np.linspace(0.0, 1.0, 10)
        y = np.column_stack([np.arange(10), np.arange(10) ** 2])
        system = "Stub"
        params: dict = {}
        integrator = "test"

    dest = write_csv(_Stub(), tmp_path / "stub.csv")
    out = read_csv(dest)
    np.testing.assert_array_equal(out["t"], _Stub.t)
    np.testing.assert_array_equal(out["y"], _Stub.y)


def test_csv_rejects_object_without_t_or_y() -> None:
    class _NoFields:
        pass

    with pytest.raises(TypeError, match=".t and .y"):
        write_csv(_NoFields(), "/tmp/nope.csv")


def test_csv_read_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="trajectory CSV"):
        read_csv(tmp_path / "does-not-exist.csv")


def test_csv_read_rejects_single_column_file(tmp_path: Path) -> None:
    bad = tmp_path / "1col.csv"
    bad.write_text("t\n0.0\n1.0\n2.0\n")
    with pytest.raises(ValueError, match="only 1 column"):
        read_csv(bad)


# --- NPZ --------------------------------------------------------------


def test_npz_round_trip_preserves_arrays_and_metadata(tmp_path: Path) -> None:
    traj = _make_traj()
    dest = write_npz(traj, tmp_path / "lorenz.npz")
    assert dest.exists()
    assert dest.stat().st_size > 0
    out = read_npz(dest)
    np.testing.assert_array_equal(out["t"], traj.t)
    np.testing.assert_array_equal(out["y"], traj.y)
    assert out["system"] == "Lorenz"
    assert out["integrator"] == "RK45"
    # The params dict round-trips with float values.
    assert out["params"]["sigma"] == pytest.approx(10.0)
    assert out["params"]["rho"] == pytest.approx(28.0)
    assert out["params"]["beta"] == pytest.approx(8.0 / 3.0)


def test_npz_is_compressed_relative_to_raw_size(tmp_path: Path) -> None:
    """Compressed binary should be smaller than the equivalent CSV
    text-encoding (per-sample %.18e widens each float to ~25 chars)."""
    traj = _make_traj(n=2000)
    csv_path = write_csv(traj, tmp_path / "lorenz.csv")
    npz_path = write_npz(traj, tmp_path / "lorenz.npz")
    assert npz_path.stat().st_size < csv_path.stat().st_size


def test_npz_via_string_path(tmp_path: Path) -> None:
    traj = _make_traj(50)
    dest = write_npz(traj, str(tmp_path / "x.npz"))
    out = read_npz(str(dest))
    assert out["system"] == "Lorenz"


def test_npz_read_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="trajectory NPZ"):
        read_npz(tmp_path / "does-not-exist.npz")


def test_npz_read_raises_on_missing_archive_entry(tmp_path: Path) -> None:
    """A foreign NPZ lacking our required keys must fail clearly."""
    bad = tmp_path / "foreign.npz"
    np.savez_compressed(bad, only_array=np.zeros(3))
    with pytest.raises(KeyError, match="missing required entry"):
        read_npz(bad)


def test_npz_handles_empty_params(tmp_path: Path) -> None:
    """A trajectory with no parameters (e.g. HenonHeiles) round-trips
    with an empty dict, not a missing key."""
    from chaotic_systems.systems import HenonHeiles

    hh = HenonHeiles()
    traj = hh.simulate((0.0, 2.0), n_points=40, integrator="RK45")
    assert traj.params == {}
    dest = write_npz(traj, tmp_path / "hh.npz")
    out = read_npz(dest)
    assert out["params"] == {}
    assert out["system"] == "HenonHeiles"
