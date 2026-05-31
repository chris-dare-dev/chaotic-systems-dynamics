#!/usr/bin/env python3
"""Programmatic post-condition verifiers for the /draft-proposal pipeline.

Usage:
  verify.py <ID> phase-1   # source brief landed + non-empty + has Items
  verify.py <ID> phase-2   # draft.md + sequencing.md shape, anti-anchoring soft-check
  verify.py <ID> phase-3   # critique.md shape, 9-axis tables, calibration sum
  verify.py <ID> phase-4   # final docs/proposals/<slug>-<DATE>.md shape
  verify.py <ID> phase-5   # git log diff vs. init_head_sha (rogue-commit guard)

The pipeline orchestrator MUST run the corresponding `verify.py` BEFORE
calling `checkpoint.py <ID> <next-phase>`. Verifier exit 0 = the
artefact on disk satisfies its phase contract; non-zero = STOP and
fix.

This script is the Q2-2026 "agent returned != agent succeeded"
gate identified as the highest-ROI architectural change in the
2026-05-19 adversary review (finding F2).

The verifier inspects ARTEFACTS ON DISK, not state.json claims —
state.json is a cache; the filesystem is the source of truth.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# Windows consoles default to cp1252, which cannot encode the em-dashes used in
# some PASS/FAIL messages below; force UTF-8 so behaviour matches Linux/macOS.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):  # pragma: no cover - non-TextIO stream
        pass


def _repo_root() -> Path:
    """Resolve the parent repo root.

    Path layout: .claude/scripts/draft-proposal/verify.py
    parents[3] = repo root.
    """
    return Path(__file__).resolve().parents[3]


def _state_path(uid: str) -> Path:
    return _repo_root() / ".claude" / "notes" / "draft-proposals" / uid / "state.json"


def _load_state(uid: str) -> dict:
    sp = _state_path(uid)
    if not sp.exists():
        sys.exit(
            f"FAIL: state.json not found at {sp}. Run init-draft-proposal.sh first."
        )
    return json.loads(sp.read_text(encoding="utf-8"))


def _read_or_fail(path: Path, what: str) -> str:
    if not path.exists():
        sys.exit(f"FAIL [{what}]: file does not exist at {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        sys.exit(f"FAIL [{what}]: file at {path} is empty")
    return text


def _assert(cond: bool, what: str, detail: str = "") -> None:
    if not cond:
        msg = f"FAIL [{what}]"
        if detail:
            msg += f": {detail}"
        sys.exit(msg)


def _count_item_headers(text: str) -> int:
    """Count `### ` H3 headers inside the `## Items` section.

    The drafter / refiner emit one H3 per item; the count is the
    pipeline's canonical item count.
    """
    # Find the Items section.
    items_match = re.search(r"^## Items\s*$", text, re.MULTILINE)
    if items_match is None:
        return 0
    start = items_match.end()
    # Find the next H2 (or EOF).
    next_h2 = re.search(r"^## ", text[start:], re.MULTILINE)
    end = start + next_h2.start() if next_h2 else len(text)
    items_block = text[start:end]
    return len(re.findall(r"^### ", items_block, re.MULTILINE))


def _parse_sequencing_rows(text: str) -> list[dict[str, str]]:
    """Parse the markdown table under `## Sequencing table`.

    Returns one dict per row with keys order, item, effort, why.
    Header / separator rows are skipped.
    """
    seq_match = re.search(r"^## Sequencing table\s*$", text, re.MULTILINE)
    if seq_match is None:
        return []
    start = seq_match.end()
    next_h2 = re.search(r"^## ", text[start:], re.MULTILINE)
    end = start + next_h2.start() if next_h2 else len(text)
    block = text[start:end]
    rows: list[dict[str, str]] = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        # Skip header + separator rows
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells or cells[0].lower() == "order":
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if len(cells) < 4:
            continue
        rows.append(
            {
                "order": cells[0],
                "item": cells[1],
                "effort": cells[2],
                "why": cells[3],
            }
        )
    return rows


def _dag_no_cycles(rows: list[dict[str, str]]) -> tuple[bool, str]:
    """Verify "depends on #N" references point to smaller row numbers.

    Returns (ok, reason). A topological sort is implicit in the
    "depends on #N where N < order" check, because if every dep is
    upstream the DAG is acyclic.
    """
    orders = []
    for r in rows:
        try:
            orders.append(int(r["order"]))
        except ValueError:
            return False, f"row has non-integer order: {r}"
    max_order = max(orders) if orders else 0
    for r in rows:
        why = r["why"].lower()
        for match in re.finditer(r"depends on #(\d+)", why):
            dep = int(match.group(1))
            if dep < 1 or dep > max_order:
                return False, (
                    f"row {r['order']} depends on #{dep} which is out of range "
                    f"[1, {max_order}]"
                )
            if dep >= int(r["order"]):
                return False, (
                    f"row {r['order']} depends on #{dep} which is not "
                    "upstream — potential DAG cycle or forward reference"
                )
    return True, ""


# ---------------------------------------------------------------------------
# Phase verifiers
# ---------------------------------------------------------------------------


def verify_phase_1(uid: str) -> None:
    """Phase 1 (resolve) -> source brief written + non-empty + has Items."""
    state = _load_state(uid)
    brief_path = state.get("source_brief_path")
    _assert(
        bool(brief_path),
        "phase-1 source_brief_path",
        "state.json source_brief_path is empty; Phase 1 didn't record the path",
    )
    p = Path(brief_path)
    text = _read_or_fail(p, "phase-1 source-brief")
    n_items = _count_item_headers(text)
    if state.get("source_kind") in ("csc-items", "single-csc"):
        resolved = state.get("resolved_csc_items") or []
        _assert(
            len(resolved) > 0,
            "phase-1 resolved_csc_items",
            "csc-items source kind but no CSC items recorded in state",
        )
        # The brief must contain one H3 per resolved CSC.
        _assert(
            n_items >= len(resolved),
            "phase-1 source-brief item count",
            f"expected >= {len(resolved)} H3 items in brief; found {n_items}",
        )
    else:
        # Freeform: at least an H1 + some content.
        _assert(
            "# " in text,
            "phase-1 source-brief shape",
            "freeform brief has no H1",
        )
    print(f"PASS phase-1 ({uid}): brief OK at {p}, items={n_items}")


def verify_phase_2(uid: str) -> None:
    """Phase 2 (draft + sequencing) — file shapes + DAG + anti-anchor soft-check."""
    state = _load_state(uid)
    draft_path = state.get("draft_path") or (
        str(_repo_root() / ".claude" / "notes" / "draft-proposals"
            / uid / "artifacts" / "draft.md")
    )
    seq_path = state.get("sequencing_path") or (
        str(_repo_root() / ".claude" / "notes" / "draft-proposals"
            / uid / "artifacts" / "sequencing.md")
    )
    draft_text = _read_or_fail(Path(draft_path), "phase-2 draft.md")
    seq_text = _read_or_fail(Path(seq_path), "phase-2 sequencing.md")

    # Drafter shape
    _assert(
        "<!-- SEQUENCING_TABLE_GOES_HERE -->" in draft_text,
        "phase-2 drafter marker",
        "draft.md missing the SEQUENCING_TABLE_GOES_HERE marker",
    )
    _assert(
        re.search(r"^## Items\s*$", draft_text, re.MULTILINE) is not None,
        "phase-2 drafter Items header",
        "draft.md missing the `## Items` H2",
    )
    n_draft_items = _count_item_headers(draft_text)
    _assert(
        n_draft_items >= 1,
        "phase-2 drafter item count",
        "draft.md has 0 items in `## Items` block",
    )

    # Sequencer shape
    rows = _parse_sequencing_rows(seq_text)
    _assert(
        len(rows) >= 1,
        "phase-2 sequencer table",
        "sequencing.md missing a parseable `## Sequencing table` with rows",
    )
    _assert(
        len(rows) == n_draft_items,
        "phase-2 row/item count match",
        f"sequencing.md rows ({len(rows)}) != draft.md items ({n_draft_items})",
    )

    # DAG well-formed
    ok, why = _dag_no_cycles(rows)
    _assert(ok, "phase-2 DAG well-formed", why)

    # Anti-anchoring soft-check: sequencer should NOT reproduce
    # large item-body prose from the draft. Heuristic: if any
    # 80-character substring of the draft's first item body appears
    # verbatim in sequencing.md, flag.
    draft_first_item_match = re.search(
        r"^###[^\n]+\n(.+?)(?=^###|\Z)", draft_text, re.MULTILINE | re.DOTALL
    )
    if draft_first_item_match:
        first_body = draft_first_item_match.group(1).strip()
        # Sample a few 80-char windows; if any leak, flag.
        leaked = False
        for start in range(0, max(len(first_body) - 80, 1), 80):
            chunk = first_body[start : start + 80].strip()
            if len(chunk) >= 80 and chunk in seq_text:
                leaked = True
                leaked_chunk = chunk[:60] + "..."
                break
        if leaked:
            sys.exit(
                "FAIL [phase-2 anti-anchoring]: sequencing.md contains an "
                f"80-char prose chunk from draft.md ({leaked_chunk!r}). The "
                "sequencer was told NOT to read the drafter's output."
            )

    print(
        f"PASS phase-2 ({uid}): draft.md OK ({n_draft_items} items), "
        f"sequencing.md OK ({len(rows)} rows, DAG well-formed, "
        "anti-anchor clean)"
    )


def verify_phase_3(uid: str) -> None:
    """Phase 3 (critique) — shape + 9-axis tables + calibration sum."""
    state = _load_state(uid)
    critique_path = state.get("critique_path") or (
        str(_repo_root() / ".claude" / "notes" / "draft-proposals"
            / uid / "artifacts" / "critique.md")
    )
    draft_path = state.get("draft_path")
    text = _read_or_fail(Path(critique_path), "phase-3 critique.md")
    draft_text = _read_or_fail(Path(draft_path), "phase-3 reference draft.md")

    _assert(
        re.search(r"^## Per-item axes\s*$", text, re.MULTILINE) is not None,
        "phase-3 Per-item axes header",
        "critique.md missing the `## Per-item axes` H2",
    )
    _assert(
        re.search(r"^## Calibration check\s*$", text, re.MULTILINE) is not None,
        "phase-3 Calibration check header",
        "critique.md missing the `## Calibration check` H2",
    )

    # Item-count parity with the draft
    n_draft_items = _count_item_headers(draft_text)
    n_critique_items = len(re.findall(r"^### ", text, re.MULTILINE))
    _assert(
        n_critique_items >= n_draft_items,
        "phase-3 item coverage",
        f"critique.md covers {n_critique_items} items but draft.md has "
        f"{n_draft_items}; critic must touch every item",
    )

    # Calibration sum check — extract the BLOCKER/MAJOR/MINOR/NONE numbers
    cal_block_match = re.search(
        r"^## Calibration check.*?(?=^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if cal_block_match:
        block = cal_block_match.group(0)
        counts = {}
        for sev in ("BLOCKER", "MAJOR", "MINOR", "NONE"):
            m = re.search(rf"{sev}[:\s]+(\d+)", block, re.IGNORECASE)
            counts[sev] = int(m.group(1)) if m else 0
        total = sum(counts.values())
        expected = 9 * n_draft_items  # 9-axis rubric (post-remediation)
        if total != expected:
            sys.exit(
                f"FAIL [phase-3 calibration arithmetic]: counts sum to {total} "
                f"but expected {expected} (= 9 axes x {n_draft_items} items). "
                f"Counts: {counts}"
            )

    print(
        f"PASS phase-3 ({uid}): critique.md OK ({n_critique_items} item "
        f"sections, calibration sum matches 9 x {n_draft_items})"
    )


def verify_phase_4(uid: str) -> None:
    """Phase 4 (refine) — final docs/proposals/<slug>-<DATE>.md shape."""
    state = _load_state(uid)
    final_path = state.get("final_proposal_path")
    _assert(
        bool(final_path),
        "phase-4 final_proposal_path",
        "state.json final_proposal_path is empty",
    )
    p = _repo_root() / final_path if not Path(final_path).is_absolute() else Path(final_path)
    text = _read_or_fail(p, "phase-4 final proposal")

    # Filename ↔ H1 date match
    slug = state.get("slug", "")
    date_stamp = state.get("date_stamp") or state.get("date") or ""
    expected_filename = f"{slug}-{date_stamp}.md"
    _assert(
        p.name == expected_filename,
        "phase-4 filename",
        f"expected {expected_filename}, got {p.name}",
    )
    h1_match = re.search(r"^# (.+?)\s*$", text, re.MULTILINE)
    _assert(
        h1_match is not None,
        "phase-4 H1 present",
        "final file has no H1 title",
    )
    if h1_match and date_stamp:
        _assert(
            date_stamp in h1_match.group(1),
            "phase-4 H1 date",
            f"H1 {h1_match.group(1)!r} does not contain the filename date "
            f"{date_stamp!r}",
        )

    # Risks populated — no `(populated after critique)` placeholders
    _assert(
        "(populated after critique)" not in text,
        "phase-4 risks populated",
        "final file still contains `(populated after critique)` placeholder",
    )

    # TL;DR claimed count vs actual Items count
    n_items_final = _count_item_headers(text)
    tldr_match = re.search(
        r"^## TL;DR\s*\n(.+?)(?=^## )", text, re.MULTILINE | re.DOTALL
    )
    if tldr_match:
        tldr_text = tldr_match.group(1)
        # Look for a number-of-items claim
        num_claim = re.search(r"(\d+)\s+items?", tldr_text)
        if num_claim:
            claimed = int(num_claim.group(1))
            if claimed != n_items_final:
                sys.exit(
                    f"FAIL [phase-4 TL;DR-Items count]: TL;DR claims "
                    f"{claimed} items but `## Items` has {n_items_final}"
                )

    # Sequencing table DAG re-validation against renumbered rows
    rows = _parse_sequencing_rows(text)
    if rows:
        ok, why = _dag_no_cycles(rows)
        _assert(ok, "phase-4 final DAG well-formed", why)
        _assert(
            len(rows) == n_items_final,
            "phase-4 sequencing/items parity",
            f"final sequencing rows ({len(rows)}) != items ({n_items_final})",
        )

    # /milestone-pipeline parseability: every item has What/Where/SOTA/Effort/Rationale
    items_block_match = re.search(
        r"^## Items.*?(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    if items_block_match:
        items_block = items_block_match.group(0)
        per_item_sections = re.split(r"^### ", items_block, flags=re.MULTILINE)[1:]
        for i, sec in enumerate(per_item_sections, start=1):
            for required_field in ("What:", "Where:", "SOTA reference:", "Effort:", "Rationale:"):
                if required_field not in sec:
                    sys.exit(
                        f"FAIL [phase-4 milestone-pipeline parseability]: "
                        f"item #{i} in `## Items` missing required field "
                        f"`{required_field}`"
                    )

    print(
        f"PASS phase-4 ({uid}): final proposal OK at {p}, "
        f"{n_items_final} items, all fields present, DAG well-formed"
    )


def verify_phase_5(uid: str) -> None:
    """Phase 5 — git log diff vs. init_head_sha; refuses if rogue commits landed."""
    state = _load_state(uid)
    init_sha = state.get("init_head_sha")
    if not init_sha:
        # If the init script didn't record it (older state), this is a soft
        # warning rather than a failure — but flag it.
        print(
            f"WARN phase-5 ({uid}): no init_head_sha in state.json; "
            "skipping rogue-commit check (consider re-init for new runs)"
        )
        return
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=True,
        )
        current_sha = result.stdout.strip()
    except subprocess.CalledProcessError as exc:
        sys.exit(f"FAIL [phase-5 git rev-parse]: {exc.stderr}")
    if current_sha != init_sha:
        # Compute the rogue commit list
        try:
            log_result = subprocess.run(
                ["git", "log", "--oneline", f"{init_sha}..{current_sha}"],
                cwd=_repo_root(),
                capture_output=True,
                text=True,
                check=True,
            )
            rogue_log = log_result.stdout.strip()
        except subprocess.CalledProcessError:
            rogue_log = "(could not compute)"
        sys.exit(
            "FAIL [phase-5 rogue-commit guard]: HEAD has moved during the "
            f"pipeline run.\n  init HEAD: {init_sha}\n  current HEAD: {current_sha}\n"
            f"  rogue commits:\n{rogue_log}\n"
            "An agent committed under the loose tool-allowlist dispatch (G4). "
            "Either revert these commits or acknowledge them explicitly by "
            "re-running init to update init_head_sha."
        )
    print(f"PASS phase-5 ({uid}): HEAD unchanged ({init_sha[:7]}) — no rogue commits")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


VERIFIERS = {
    "phase-1": verify_phase_1,
    "phase-2": verify_phase_2,
    "phase-3": verify_phase_3,
    "phase-4": verify_phase_4,
    "phase-5": verify_phase_5,
}


def main(argv: list[str]) -> None:
    if len(argv) != 3:
        sys.exit(__doc__)
    uid, phase = argv[1], argv[2]
    if phase not in VERIFIERS:
        sys.exit(
            f"unknown phase: {phase}. Valid: {', '.join(VERIFIERS.keys())}"
        )
    VERIFIERS[phase](uid)


if __name__ == "__main__":
    main(sys.argv)
