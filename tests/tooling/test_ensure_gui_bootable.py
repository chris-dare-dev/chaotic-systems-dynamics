"""Tests for the cross-platform GUI-bootability preflight.

PT2 — docs/proposals/python-only-pipeline-tooling-2026-05-31.md. Covers the
pure-Python replacement for ``ensure-gui-bootable.sh``:

- cross-platform venv interpreter discovery (``.venv/bin/python`` POSIX vs
  ``.venv/Scripts/python.exe`` Windows, detected by filesystem probe);
- the missing-venv recovery message;
- the ``main`` exit-code plumbing (green -> 0, red -> probe's code), both via a
  faked ``subprocess.run`` and via a REAL subprocess running a trivial probe
  (so the cross-platform wrapper -- the thing PT2 actually changed -- is
  exercised end-to-end without needing a GL-capable host);
- one best-effort live-GUI boot that asserts green where OpenGL/VTK is
  available and SKIPS (never fails) where it is not -- the embedded pyvistaqt
  3D viewport cannot get a pixel format headless on a bare Windows box.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = (
    _REPO_ROOT / ".claude" / "scripts" / "frontend-uplift" / "ensure_gui_bootable.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ensure_gui_bootable_uut", _MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


egb = _load()


def test_module_exists() -> None:
    assert _MODULE_PATH.is_file()


# --------------------------------------------------------------------------- #
# find_venv_python — cross-platform layout discovery
# --------------------------------------------------------------------------- #


def test_find_venv_python_windows_layout(tmp_path: Path) -> None:
    win = tmp_path / ".venv" / "Scripts"
    win.mkdir(parents=True)
    exe = win / "python.exe"
    exe.write_text("", encoding="utf-8")
    assert egb.find_venv_python(tmp_path) == exe


def test_find_venv_python_posix_layout(tmp_path: Path) -> None:
    posix = tmp_path / ".venv" / "bin"
    posix.mkdir(parents=True)
    py = posix / "python"
    py.write_text("", encoding="utf-8")
    assert egb.find_venv_python(tmp_path) == py


def test_find_venv_python_none_when_absent(tmp_path: Path) -> None:
    assert egb.find_venv_python(tmp_path) is None


def test_find_venv_python_returns_existing_file(tmp_path: Path) -> None:
    # When both layouts exist, the returned path must actually be on disk.
    (tmp_path / ".venv" / "Scripts").mkdir(parents=True)
    (tmp_path / ".venv" / "Scripts" / "python.exe").write_text("", encoding="utf-8")
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    result = egb.find_venv_python(tmp_path)
    assert result is not None and result.is_file()


# --------------------------------------------------------------------------- #
# recovery_message
# --------------------------------------------------------------------------- #


def test_recovery_message_contents(tmp_path: Path) -> None:
    msg = egb.recovery_message(tmp_path)
    assert str(tmp_path / ".venv") in msg
    assert "python -m venv .venv" in msg
    # Both activation forms (the bash script showed only the POSIX one).
    assert "source .venv/bin/activate" in msg
    assert ".venv\\Scripts\\activate" in msg
    assert 'pip install -e ".[dev]"' in msg
    assert "/frontend-uplift" in msg


# --------------------------------------------------------------------------- #
# main — exit-code plumbing (faked subprocess; no real GUI)
# --------------------------------------------------------------------------- #


def test_main_missing_venv_returns_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setattr(egb.common, "repo_root", lambda: tmp_path)
    rc = egb.main([])
    assert rc == 1
    err = capsys.readouterr().err
    assert "[fail] .venv not present" in err
    assert "python -m venv .venv" in err


def test_main_green_returns_0(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setattr(egb.common, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(egb, "find_venv_python", lambda root: tmp_path / "py")
    monkeypatch.setattr(
        egb.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="BOOT_OK\n", stderr=""),
    )
    rc = egb.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "BOOT_OK" in out
    assert "[ok] GUI is bootable" in out


def test_main_red_propagates_probe_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setattr(egb.common, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(egb, "find_venv_python", lambda root: tmp_path / "py")
    monkeypatch.setattr(
        egb.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=5, stdout="IMPORT_FAIL: boom\n", stderr=""
        ),
    )
    rc = egb.main([])
    assert rc == 5
    captured = capsys.readouterr()
    assert "IMPORT_FAIL: boom" in captured.out
    assert "rc=5" in captured.err


def test_main_passes_offscreen_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(egb.common, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(egb, "find_venv_python", lambda root: tmp_path / "py")
    seen: dict[str, object] = {}

    def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
        seen["cmd"] = cmd
        seen["env"] = kwargs.get("env")
        return SimpleNamespace(returncode=0, stdout="BOOT_OK", stderr="")

    monkeypatch.setattr(egb.subprocess, "run", fake_run)
    egb.main([])
    # The venv interpreter is invoked with -c <probe>, under offscreen Qt.
    assert seen["cmd"][0] == str(tmp_path / "py")
    assert seen["cmd"][1] == "-c"
    assert seen["env"]["QT_QPA_PLATFORM"] == "offscreen"


# --------------------------------------------------------------------------- #
# main — REAL subprocess, trivial probe (end-to-end wrapper; no GL needed)
# --------------------------------------------------------------------------- #


def test_main_real_subprocess_green(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """Genuine path -- find_venv_python -> subprocess.run of a real interpreter
    -> exit-code relay -> ``[ok]`` print -- without a GL-capable host. We point
    the "venv interpreter" at the current real interpreter and swap the
    GUI-construct probe for a trivial one that just prints BOOT_OK. This proves
    the cross-platform wrapper (what PT2 actually changed) works; the GUI's own
    bootability is covered by tests/gui + tests/visualization.
    """
    monkeypatch.setattr(egb.common, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(egb, "find_venv_python", lambda root: Path(sys.executable))
    monkeypatch.setattr(egb, "_PROBE_SRC", "print('BOOT_OK')")
    rc = egb.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "BOOT_OK" in out
    assert "[ok] GUI is bootable" in out


def test_main_real_subprocess_red(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """Same real-subprocess path, but the probe exits non-zero -> main relays it."""
    monkeypatch.setattr(egb.common, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(egb, "find_venv_python", lambda root: Path(sys.executable))
    monkeypatch.setattr(
        egb, "_PROBE_SRC", "print('BOOT_FAIL: simulated'); import sys; sys.exit(6)"
    )
    rc = egb.main([])
    captured = capsys.readouterr()
    assert rc == 6
    assert "BOOT_FAIL: simulated" in captured.out
    assert "rc=6" in captured.err


# --------------------------------------------------------------------------- #
# best-effort live-GUI boot (env-dependent; never fails)
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    egb.find_venv_python(_REPO_ROOT) is None,
    reason="project .venv not present; cannot run the real GUI bootability probe",
)
def test_real_gui_boots_green_or_skips_without_gl() -> None:
    """Optional smoke test of the REAL GUI boot.

    The full probe needs a GL-capable host (the embedded pyvistaqt 3D viewport
    cannot get an OpenGL pixel format headless on a bare Windows box). So:
    assert the green contract iff the probe returns 0; otherwise SKIP with the
    rc -- never fail. The wrapper's own logic is covered by the real-subprocess
    tests above; the GUI's correctness by tests/gui + tests/visualization.
    """
    rc = subprocess.run(
        ["python", str(_MODULE_PATH)],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    if rc.returncode == 0 and "BOOT_OK" in rc.stdout:
        assert "[ok] GUI is bootable" in rc.stdout
        return
    pytest.skip(
        f"real GUI did not boot in this environment (rc={rc.returncode}); "
        "needs a GL-capable host"
    )
