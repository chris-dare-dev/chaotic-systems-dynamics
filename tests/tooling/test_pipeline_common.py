"""Tests for the shared pipeline-tooling helpers (.claude/scripts/_pipeline_common.py).

PT1a — docs/proposals/python-only-pipeline-tooling-2026-05-31.md. Covers the
cross-platform stdlib primitives that replace the POSIX-only bash wrappers:
repo-root resolution, UTC stamping, git-head capture, mkdir -p, atomic
state.json read/write, and idempotent resume.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

# .claude/scripts/_pipeline_common.py — three dirs up from this test file:
# tests/tooling/test_pipeline_common.py -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMMON_PATH = _REPO_ROOT / ".claude" / "scripts" / "_pipeline_common.py"


def _load_common() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_pipeline_common_under_test", _COMMON_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


common = _load_common()


def test_module_exists() -> None:
    assert _COMMON_PATH.is_file()


def test_repo_root_points_at_repo() -> None:
    # The shipped module lives at .claude/scripts/_pipeline_common.py, so its
    # repo_root() must resolve to this repository (which contains pyproject.toml).
    root = common.repo_root()
    assert (root / "pyproject.toml").is_file()
    assert (root / ".claude" / "scripts").is_dir()


def test_utc_now_iso_format() -> None:
    stamp = common.utc_now_iso()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", stamp)


def test_utc_date_format() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", common.utc_date())


def test_git_head_sha_is_hex_or_empty() -> None:
    sha = common.git_head_sha()
    # In a git checkout this is a 40-char hex SHA; the contract allows "" when
    # git is unavailable (the phase-5 guard treats empty as "cannot verify").
    assert sha == "" or re.fullmatch(r"[0-9a-f]{40}", sha)


def test_git_head_sha_empty_outside_repo(tmp_path: Path) -> None:
    # A non-git directory must yield "" rather than raising.
    assert common.git_head_sha(tmp_path) == ""


def test_ensure_dirs_creates_nested(tmp_path: Path) -> None:
    a = tmp_path / "x" / "y" / "z"
    b = tmp_path / "sibling"
    common.ensure_dirs(a, b)
    assert a.is_dir() and b.is_dir()
    # Idempotent: a second call on an existing tree must not raise.
    common.ensure_dirs(a, b)
    assert a.is_dir()


def test_write_then_read_state_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    payload = {"phase": "init", "unicode": "rho rises -> peak", "n": 3}
    common.write_state_atomic(p, payload)
    assert common.read_state(p) == payload


def test_write_state_is_utf8(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    # A non-ASCII value must round-trip regardless of platform code page. The
    # file is written with json's default ensure_ascii=True (matching the
    # former bash heredocs byte-for-byte), so the bytes contain the \uXXXX
    # escape; the contract is that read_state decodes it back to the char.
    common.write_state_atomic(p, {"phase": "init", "note": "ρ→—"})
    assert p.read_bytes().decode("utf-8")  # decodable as UTF-8, no crash
    assert common.read_state(p)["note"] == "ρ→—"


def test_write_state_atomic_leaves_no_tmp(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    common.write_state_atomic(p, {"phase": "init"})
    assert not (tmp_path / "state.json.tmp").exists()


def test_resume_if_exists_false_when_absent(tmp_path: Path) -> None:
    assert common.resume_if_exists(tmp_path / "nope.json") is False


def test_resume_if_exists_true_and_prints(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "state.json"
    common.write_state_atomic(p, {"phase": "draft-running"})
    assert common.resume_if_exists(p) is True
    out = capsys.readouterr().out
    assert "resuming" in out
    assert "draft-running" in out


def test_real_module_is_importable_as_subprocess() -> None:
    # The shipped module must import cleanly under the active interpreter with
    # no third-party dependencies (stdlib-only constraint).
    result = subprocess.run(
        ["python", "-c", f"import importlib.util,sys;"
         f"s=importlib.util.spec_from_file_location('m',r'{_COMMON_PATH}');"
         f"m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
         f"print(m.utc_date())"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}\s*", result.stdout)
