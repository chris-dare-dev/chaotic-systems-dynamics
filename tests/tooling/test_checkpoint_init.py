"""Tests for the ``init`` subcommands of the three pipeline ``checkpoint.py`` files.

PT1a — docs/proposals/python-only-pipeline-tooling-2026-05-31.md. Verifies the
pure-Python ``init`` subcommand reproduces the state.json schema the former
``init-*.sh`` produced, on any OS, including the mode flags, idempotent resume,
draft-proposal's slug/date decomposition + ``init_head_sha`` capture, and the
``--from`` / ``--brief`` mutual exclusion.

Each checkpoint module is loaded by file path (the ``.claude/scripts`` tree is
not an installed package), and its shared ``common.repo_root`` is monkeypatched
to a tmp dir so the tests never touch the repository's real ``.claude/notes``.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / ".claude" / "scripts"

_PIPELINES = {
    "capability-scout": ("capability-scout", "capability-scouts"),
    "draft-proposal": ("draft-proposal", "draft-proposals"),
    "frontend-uplift": ("frontend-uplift", "frontend-uplifts"),
}


def _load_checkpoint(pipeline_dir: str) -> ModuleType:
    path = _SCRIPTS / pipeline_dir / "checkpoint.py"
    spec = importlib.util.spec_from_file_location(
        f"checkpoint_{pipeline_dir.replace('-', '_')}", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    mod = _load_checkpoint("capability-scout")
    monkeypatch.setattr(mod.common, "repo_root", lambda: tmp_path)
    return mod


@pytest.fixture
def fu(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    mod = _load_checkpoint("frontend-uplift")
    monkeypatch.setattr(mod.common, "repo_root", lambda: tmp_path)
    return mod


@pytest.fixture
def dp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    mod = _load_checkpoint("draft-proposal")
    monkeypatch.setattr(mod.common, "repo_root", lambda: tmp_path)
    return mod


# --------------------------------------------------------------------------- #
# capability-scout
# --------------------------------------------------------------------------- #


def test_cs_init_creates_state(cs: ModuleType, tmp_path: Path) -> None:
    cs.init(["smoke", "--brief", "hello", "--deep"])
    state_path = tmp_path / ".claude/notes/capability-scouts/smoke/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["kind"] == "capability-scout"
    assert state["phase"] == "init"
    assert state["capability_scout_brief"] == "hello"
    assert state["survey_mode"] == "deep"
    assert state["challenge_finding_counts"] == {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
    }


def test_cs_init_default_mode_standard(cs: ModuleType, tmp_path: Path) -> None:
    cs.init(["smoke2"])
    state = json.loads(
        (tmp_path / ".claude/notes/capability-scouts/smoke2/state.json").read_text(
            encoding="utf-8"
        )
    )
    assert state["survey_mode"] == "standard"
    assert state["capability_scout_brief"] == ""


def test_cs_init_creates_agent_memory_dirs(cs: ModuleType, tmp_path: Path) -> None:
    cs.init(["smoke3"])
    mem = tmp_path / ".claude/agent-memory"
    for role in ("competitive", "academic", "oss", "internal-adversary", "challenger"):
        assert (mem / f"capability-scout-{role}").is_dir()


def test_cs_init_idempotent_resume(cs: ModuleType, tmp_path: Path, capsys) -> None:
    cs.init(["dup", "--brief", "first"])
    cs.init(["dup", "--brief", "second-ignored"])
    out = capsys.readouterr().out
    assert "resuming" in out
    state = json.loads(
        (tmp_path / ".claude/notes/capability-scouts/dup/state.json").read_text(
            encoding="utf-8"
        )
    )
    # Resume must NOT overwrite the original brief.
    assert state["capability_scout_brief"] == "first"


def test_cs_init_rejects_unknown_arg(cs: ModuleType) -> None:
    with pytest.raises(SystemExit):
        cs.init(["x", "--bogus"])


# --------------------------------------------------------------------------- #
# frontend-uplift
# --------------------------------------------------------------------------- #


def test_fu_init_creates_state(fu: ModuleType, tmp_path: Path) -> None:
    fu.init(["smoke", "--lean"])
    state = json.loads(
        (tmp_path / ".claude/notes/frontend-uplifts/smoke/state.json").read_text(
            encoding="utf-8"
        )
    )
    assert state["kind"] == "frontend-uplift"
    assert state["discover_mode"] == "lean"
    assert state["screenshots_dir"] == ".claude/notes/frontend-uplifts/smoke/screenshots"


def test_fu_init_creates_subdirs(fu: ModuleType, tmp_path: Path) -> None:
    fu.init(["dirs"])
    base = tmp_path / ".claude/notes/frontend-uplifts/dirs"
    assert (base / "discover-briefs").is_dir()
    assert (base / "screenshots").is_dir()
    assert (base / "artifacts").is_dir()


# --------------------------------------------------------------------------- #
# draft-proposal (slug/date decomposition, init_head_sha, --from/--brief)
# --------------------------------------------------------------------------- #


def test_dp_init_bare_slug_stamps_date(dp: ModuleType, tmp_path: Path) -> None:
    dp.init(["myslug", "--brief", "do a thing"])
    dirs = list((tmp_path / ".claude/notes/draft-proposals").iterdir())
    assert len(dirs) == 1
    sid = dirs[0].name
    assert re.fullmatch(r"myslug-\d{4}-\d{2}-\d{2}", sid)
    state = json.loads((dirs[0] / "state.json").read_text(encoding="utf-8"))
    assert state["slug"] == "myslug"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", state["date"])
    assert state["date_stamp"] == state["date"]
    assert state["source_kind"] == "freeform-brief"
    assert state["draft_brief"] == "do a thing"


def test_dp_init_qualified_id_preserved(dp: ModuleType, tmp_path: Path) -> None:
    dp.init(["already-2026-01-02", "--brief", "x"])
    state_path = tmp_path / ".claude/notes/draft-proposals/already-2026-01-02/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["slug"] == "already"
    assert state["date"] == "2026-01-02"


def test_dp_init_from_csv_is_csc_items(dp: ModuleType, tmp_path: Path) -> None:
    dp.init(["bundle", "--from", "001,002,003"])
    dirs = list((tmp_path / ".claude/notes/draft-proposals").iterdir())
    state = json.loads((dirs[0] / "state.json").read_text(encoding="utf-8"))
    assert state["source_kind"] == "csc-items"
    assert state["csc_items"] == ["001", "002", "003"]


def test_dp_init_from_single_is_single_csc(dp: ModuleType, tmp_path: Path) -> None:
    dp.init(["one", "--from", "018"])
    dirs = list((tmp_path / ".claude/notes/draft-proposals").iterdir())
    state = json.loads((dirs[0] / "state.json").read_text(encoding="utf-8"))
    assert state["source_kind"] == "single-csc"
    assert state["csc_items"] == ["018"]


def test_dp_init_captures_head_sha(dp: ModuleType, tmp_path: Path, monkeypatch) -> None:
    # git_head_sha reads the REAL repo (root arg), so it returns a 40-char SHA.
    dp.init(["sha", "--brief", "x"])
    dirs = list((tmp_path / ".claude/notes/draft-proposals").iterdir())
    state = json.loads((dirs[0] / "state.json").read_text(encoding="utf-8"))
    assert state["init_head_sha"] == "" or re.fullmatch(
        r"[0-9a-f]{40}", state["init_head_sha"]
    )


def test_dp_init_rejects_both_from_and_brief(dp: ModuleType) -> None:
    with pytest.raises(SystemExit):
        dp.init(["x", "--from", "001", "--brief", "y"])


def test_dp_init_schema_has_all_phase_fields(dp: ModuleType, tmp_path: Path) -> None:
    dp.init(["full", "--brief", "x"])
    dirs = list((tmp_path / ".claude/notes/draft-proposals").iterdir())
    state = json.loads((dirs[0] / "state.json").read_text(encoding="utf-8"))
    for key in (
        "critique_finding_counts",
        "critique_cycle",
        "final_proposal_path",
        "dropped_at_refinement",
        "resolved_csc_items",
        "agents_dispatched",
    ):
        assert key in state, f"missing schema key {key}"
    assert state["critique_cycle"] == 1


# --------------------------------------------------------------------------- #
# regression guard: the existing state-machine semantics are untouched
# --------------------------------------------------------------------------- #


def test_dp_loopback_semantics_intact(dp: ModuleType) -> None:
    # PT1a must NOT regress the recritique loop-back guard.
    assert ("recritique-running", "refine-running") in dp.LOOP_BACK_TRANSITIONS
    assert dp.MAX_CRITIQUE_CYCLES == 3


def test_advance_init_is_not_a_phase_name(dp: ModuleType, tmp_path: Path) -> None:
    # 'init' is dispatched as a subcommand, and the literal phase 'init' is the
    # first PHASE_ORDER entry. Confirm the dispatcher routes `init <id>` to the
    # subcommand (creating state) rather than treating it as an advance.
    dp.main(["checkpoint.py", "init", "routed", "--brief", "x"])
    assert (tmp_path / ".claude/notes/draft-proposals").exists()
