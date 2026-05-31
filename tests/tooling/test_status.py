"""Tests for the ``status`` subcommand of the three pipeline ``checkpoint.py`` files.

PT1b — docs/proposals/python-only-pipeline-tooling-2026-05-31.md.

**In-process golden tests** (bash-independent): a crafted state.json with fixed
timestamps is rendered by the Python ``status`` function and the output is
asserted line by line — pinning labels, column widths, the phase-history
elapsed deltas (``+ Nm → next`` / ``+ Ns → next``), and the ``Next:`` hint.

Historical note: PT1b originally also carried opportunistic *byte-parity* tests
that ran the legacy ``status.sh`` and asserted its output matched the Python
``status`` byte-for-byte. Those proved parity while the bash scripts still
existed; PT4 (commit deleting the seven ``.sh`` files) removed the golden
reference, so the parity tests were retired here. The in-process golden tests
below now own the output contract — they pin the exact rendered lines without
needing bash at all, which is the whole point of the python-only port.
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

# pipeline-dir -> (notes-subdir, status.sh path)
_PIPELINES = {
    "capability-scout": "capability-scouts",
    "draft-proposal": "draft-proposals",
    "frontend-uplift": "frontend-uplifts",
}


def _load_checkpoint(pipeline_dir: str) -> ModuleType:
    path = _SCRIPTS / pipeline_dir / "checkpoint.py"
    spec = importlib.util.spec_from_file_location(
        f"checkpoint_status_{pipeline_dir.replace('-', '_')}", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _norm(text: str) -> str:
    """Normalize the single wall-clock-dependent token (``N min ago``)."""
    return re.sub(r"\d+ min ago", "N min ago", text)


# Crafted states with fixed, spread-out timestamps so the history elapsed
# deltas are deterministic (+30s, +5m, +4s ...).
_CS_STATE = {
    "id": "golden-cs",
    "kind": "capability-scout",
    "created_at": "2026-05-31T00:00:00Z",
    "updated_at": "2026-05-31T00:05:38Z",
    "phase": "synthesize-complete",
    "phase_history": [
        {"phase": "init", "at": "2026-05-31T00:00:00Z"},
        {"phase": "survey-running", "at": "2026-05-31T00:00:30Z"},
        {"phase": "survey-complete", "at": "2026-05-31T00:05:30Z"},
        {"phase": "synthesize-running", "at": "2026-05-31T00:05:34Z"},
        {"phase": "synthesize-complete", "at": "2026-05-31T00:05:38Z"},
    ],
    "capability_scout_brief": "x",
    "survey_mode": "deep",
    "agents_dispatched": ["competitive", "academic", "oss", "internal-adversary"],
    "agents_returned": ["competitive", "academic"],
    "survey_briefs": [],
    "synthesis_path": "artifacts/synthesis.md",
    "candidate_count": 12,
    "challenge_path": None,
    "challenge_finding_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
    "final_report_path": None,
    "ranked_candidates": [],
}

_DP_STATE = {
    "id": "golden-dp-2026-05-31",
    "kind": "draft-proposal",
    "slug": "golden-dp",
    "date": "2026-05-31",
    "date_stamp": "2026-05-31",
    "created_at": "2026-05-31T00:00:00Z",
    "updated_at": "2026-05-31T00:01:00Z",
    "init_head_sha": "0" * 40,
    "phase": "draft-complete",
    "phase_history": [
        {"phase": "init", "at": "2026-05-31T00:00:00Z"},
        {"phase": "resolve-running", "at": "2026-05-31T00:00:10Z"},
        {"phase": "resolve-complete", "at": "2026-05-31T00:00:20Z"},
        {"phase": "draft-running", "at": "2026-05-31T00:00:40Z"},
        {"phase": "draft-complete", "at": "2026-05-31T00:01:00Z"},
    ],
    "source_kind": "freeform-brief",
    "csc_items": [],
    "draft_brief": "do a thing",
    "source_brief_path": "source-brief.md",
    "resolved_csc_items": [],
    "agents_dispatched": ["drafter", "sequencer"],
    "agents_returned": ["drafter", "sequencer"],
    "draft_path": "artifacts/draft.md",
    "sequencing_path": "artifacts/sequencing.md",
    "item_count": 4,
    "critique_path": None,
    "critique_finding_counts": {"blocker": 0, "major": 0, "minor": 0, "none": 0},
    "critique_cycle": 1,
    "final_proposal_path": None,
    "final_item_count": 0,
    "dropped_at_refinement": [],
}

_FU_STATE = {
    "id": "golden-fu",
    "kind": "frontend-uplift",
    "created_at": "2026-05-31T00:00:00Z",
    "updated_at": "2026-05-31T00:02:00Z",
    "phase": "discover-complete",
    "phase_history": [
        {"phase": "init", "at": "2026-05-31T00:00:00Z"},
        {"phase": "discover-running", "at": "2026-05-31T00:00:15Z"},
        {"phase": "discover-complete", "at": "2026-05-31T00:02:00Z"},
    ],
    "frontend_uplift_brief": "x",
    "discover_mode": "lean",
    "agents_dispatched": ["visual", "library"],
    "agents_returned": ["visual"],
    "discover_briefs": ["a", "b"],
    "screenshots_dir": ".claude/notes/frontend-uplifts/golden-fu/screenshots",
    "screenshot_count": 5,
    "synthesis_path": None,
    "candidate_count": 0,
    "challenge_path": None,
    "challenge_finding_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
    "final_report_path": None,
    "ranked_candidates": [],
}

_GOLDENS = {
    "capability-scout": _CS_STATE,
    "draft-proposal": _DP_STATE,
    "frontend-uplift": _FU_STATE,
}


# --------------------------------------------------------------------------- #
# In-process golden tests (always run)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("pipeline", list(_PIPELINES))
def test_status_renders_history_deltas(
    pipeline: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    mod = _load_checkpoint(pipeline)
    state = _GOLDENS[pipeline]
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(mod, "_state_path", lambda uid: state_file)
    # frontend-uplift's status scans repo_root()/screenshots_dir; point it at an
    # empty tmp dir so it never touches the real repo during the unit test.
    if hasattr(mod, "common"):
        monkeypatch.setattr(mod.common, "repo_root", lambda: tmp_path)

    mod.status([state["id"]])
    out = capsys.readouterr().out

    # The phase-history elapsed deltas use the U+2192 arrow and >2 right-align.
    assert "+30s → survey-running" in out or "+15s → discover-running" in out or "+10s → resolve-running" in out
    # The final history entry is "(now)".
    assert "(now)" in out
    # The Next: hint resolves (no "(unknown)" for a known phase).
    assert "Next:" in out
    assert "(unknown)" not in out


def test_status_capability_scout_exact_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    mod = _load_checkpoint("capability-scout")
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(_CS_STATE), encoding="utf-8")
    monkeypatch.setattr(mod, "_state_path", lambda uid: state_file)

    mod.status(["golden-cs"])
    out = _norm(capsys.readouterr().out)

    assert "Capability-scout: golden-cs" in out
    assert "Mode:             deep" in out
    assert "Phase:            synthesize-complete (since 2026-05-31T00:05:38Z, N min ago)" in out
    assert "  init                   2026-05-31T00:00:00Z +30s → survey-running" in out
    assert "  survey-running         2026-05-31T00:00:30Z + 5m → survey-complete" in out
    assert "  synthesize-complete    2026-05-31T00:05:38Z (now)" in out
    assert "Agents:           dispatched=competitive,academic,oss,internal-adversary" in out
    assert "                  returned=competitive,academic" in out
    assert "                  pending=internal-adversary,oss" in out
    assert "Synthesis:        artifacts/synthesis.md (12 candidates)" in out
    assert "Next:             challenge-running (run Phase 3 — dispatch challenger)" in out


def test_status_draft_proposal_exact_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    mod = _load_checkpoint("draft-proposal")
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(_DP_STATE), encoding="utf-8")
    monkeypatch.setattr(mod, "_state_path", lambda uid: state_file)

    mod.status(["golden-dp-2026-05-31"])
    out = _norm(capsys.readouterr().out)

    assert "Draft-proposal: golden-dp-2026-05-31" in out
    assert "Slug:           golden-dp" in out
    assert "Source kind:    freeform-brief" in out
    assert "Brief:          (set, 10 chars)" in out
    assert "  resolve-complete       2026-05-31T00:00:20Z +20s → draft-running" in out
    assert "Draft:          artifacts/draft.md (4 items)" in out
    assert "Sequencing:     artifacts/sequencing.md" in out
    assert "Next:           critique-running (Phase 3 — dispatch critic)" in out


def test_status_frontend_uplift_exact_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    mod = _load_checkpoint("frontend-uplift")
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(_FU_STATE), encoding="utf-8")
    monkeypatch.setattr(mod, "_state_path", lambda uid: state_file)

    mod.status(["golden-fu"])
    out = _norm(capsys.readouterr().out)

    assert "Frontend-uplift: golden-fu" in out
    assert "Mode:            lean" in out
    # Delta tail pins the >2-right-aligned arrow format (the 22-col row padding
    # is already pinned by the capability-scout / draft-proposal exact tests).
    assert "+15s → discover-running" in out
    assert "+ 1m → discover-complete" in out
    # The Screenshots block only renders when the on-disk dir exists (byte-
    # parity with status.sh, which scans the filesystem); "golden-fu" has no
    # such dir under the real repo, so no Screenshots line is emitted -- and
    # there is deliberately NO "Discover briefs:" line (status.sh has none).
    assert "Discover briefs:" not in out
    assert "Next:            synthesize-running (run Phase 2 — main session merges)" in out


@pytest.mark.parametrize("pipeline", list(_PIPELINES))
def test_status_missing_state_errors_with_new_command(pipeline: str, monkeypatch, tmp_path) -> None:
    mod = _load_checkpoint(pipeline)
    monkeypatch.setattr(mod, "_state_path", lambda uid: tmp_path / "absent.json")
    with pytest.raises(SystemExit) as excinfo:
        mod.status(["nope"])
    # The not-found message points at the NEW python entrypoint, not init-*.sh.
    msg = str(excinfo.value)
    assert "checkpoint.py init" in msg
    assert ".sh" not in msg


@pytest.mark.parametrize("pipeline", list(_PIPELINES))
def test_status_routed_through_main(pipeline: str, monkeypatch, tmp_path, capsys) -> None:
    mod = _load_checkpoint(pipeline)
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(_GOLDENS[pipeline]), encoding="utf-8")
    monkeypatch.setattr(mod, "_state_path", lambda uid: state_file)
    mod.main(["checkpoint.py", "status", _GOLDENS[pipeline]["id"]])
    out = capsys.readouterr().out
    assert "Phase:" in out


def test_status_no_args_usage(monkeypatch) -> None:
    mod = _load_checkpoint("capability-scout")
    with pytest.raises(SystemExit):
        mod.status([])
