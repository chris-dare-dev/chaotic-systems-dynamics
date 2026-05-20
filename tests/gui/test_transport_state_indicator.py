"""Tests for FU-012 — transport-strip play/pause state indicator.

Pre-FU-012 the transport strip read::

    Speed: [1× v]   [=====O==========] t = 12.3 / 40.0

with no in-strip cue for whether playback was running, paused,
or idle. The only "is this playing?" affordance was the disabled
state of the *toolbar's* Pause action — invisible while the
user's gaze was on the scrubber (visual scout F-09,
``screenshots/lorenz-running.png``).

Post-FU-012 the strip carries a read-only ``QLabel`` state
indicator at its left edge that reads ``Idle`` / ``Playing`` /
``Paused``. The QSS rule
``QLabel[role="transport-state"][state="…"]`` swaps the foreground
colour per state: ``text-secondary`` for idle, ``accent`` for
playing, ``accent_pressed`` for paused — all PALETTE-routed.
Logic Pro / Ableton co-locate transport state with controls;
this mirrors that pattern.

Coverage:

- The ``transport_state`` ``QLabel`` exists, is parented to the
  transport host, and is at the left edge of the strip.
- The ``role`` dynamic property is ``"transport-state"`` (so the
  QSS rule applies); the ``state`` property defaults to ``"idle"``
  with text ``"Idle"``.
- ``_set_transport_state("playing" / "paused" / "idle")``
  updates both the ``state`` property and the displayed text in
  lock-step.
- ``_set_transport_enabled(True)`` → ``"paused"``;
  ``_set_transport_enabled(False)`` → ``"idle"`` (the boundary
  transitions when a trajectory loads / unloads).
- ``dark.qss`` carries the ``QLabel[role="transport-state"]``
  base rule plus the two state-variant rules; all three use
  PALETTE-grounded colours (text_secondary / accent /
  accent_pressed) — challenger §3 MINOR token-discipline
  mitigation.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


@pytest.fixture
def window(qtbot):  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    win = Window()
    qtbot.addWidget(win)
    yield win
    win.close()


# ---------------------------------------------------------------------------
# Label exists + correct attributes
# ---------------------------------------------------------------------------


def test_transport_state_label_exists(window) -> None:  # type: ignore[no-untyped-def]
    """The FU-012 ``transport_state`` ``QLabel`` exists on the window."""

    from PySide6.QtWidgets import QLabel

    label = window.findChild(QLabel, "transport_state")
    assert label is not None, (
        "FU-012 — transport_state QLabel missing from main window. "
        "It must be created in _build_transport_panel() and carry "
        "objectName='transport_state'."
    )
    # Pinning the attribute access path too — internal callers
    # (the live-preview pipeline, the export wrapper, future
    # transitions) reach the label via ``window.transport_state_label``.
    assert window.transport_state_label is label


def test_transport_state_label_has_role_property(window) -> None:  # type: ignore[no-untyped-def]
    """The ``role="transport-state"`` property is set so QSS matches."""

    label = window.transport_state_label
    assert label.property("role") == "transport-state", (
        "FU-012 — role property must be 'transport-state' so the "
        "QSS rule QLabel[role=\"transport-state\"] applies."
    )


def test_transport_state_defaults_to_idle(window) -> None:  # type: ignore[no-untyped-def]
    """At construction the strip reads 'Idle' (no trajectory loaded yet)."""

    label = window.transport_state_label
    assert label.property("state") == "idle", (
        "FU-012 — state property must default to 'idle' (the "
        "_set_transport_enabled(False) call at init disables the "
        "transport, which collapses the indicator to Idle)."
    )
    assert label.text() == "Idle"


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


def test_set_transport_state_to_playing(window) -> None:  # type: ignore[no-untyped-def]
    """``_set_transport_state('playing')`` updates label + state property."""

    window._set_transport_state("playing")  # noqa: SLF001
    label = window.transport_state_label
    assert label.text() == "Playing"
    assert label.property("state") == "playing"


def test_set_transport_state_to_paused(window) -> None:  # type: ignore[no-untyped-def]
    """``_set_transport_state('paused')`` updates label + state property."""

    window._set_transport_state("paused")  # noqa: SLF001
    label = window.transport_state_label
    assert label.text() == "Paused"
    assert label.property("state") == "paused"


def test_set_transport_state_to_idle(window) -> None:  # type: ignore[no-untyped-def]
    """``_set_transport_state('idle')`` updates label + state property."""

    # First flip to playing so the test isn't a no-op.
    window._set_transport_state("playing")  # noqa: SLF001
    window._set_transport_state("idle")  # noqa: SLF001
    label = window.transport_state_label
    assert label.text() == "Idle"
    assert label.property("state") == "idle"


def test_set_transport_enabled_true_marks_paused(window) -> None:  # type: ignore[no-untyped-def]
    """Enabling the transport (trajectory loaded) sets the indicator to Paused."""

    window._set_transport_enabled(True)  # noqa: SLF001
    label = window.transport_state_label
    assert label.property("state") == "paused", (
        "FU-012 — when a trajectory finishes simulating, the "
        "transport is enabled and the indicator should read "
        "'Paused' (ready to play) rather than 'Idle' (no trajectory)."
    )


def test_set_transport_enabled_false_marks_idle(window) -> None:  # type: ignore[no-untyped-def]
    """Disabling the transport collapses the indicator to Idle."""

    # First enable so the test transitions out of the init default.
    window._set_transport_enabled(True)  # noqa: SLF001
    window._set_transport_enabled(False)  # noqa: SLF001
    label = window.transport_state_label
    assert label.property("state") == "idle"


# ---------------------------------------------------------------------------
# Placement — leftmost in the transport row
# ---------------------------------------------------------------------------


def test_transport_state_label_is_leftmost_in_strip(window) -> None:  # type: ignore[no-untyped-def]
    """The state indicator sits at the left edge of the transport strip.

    Synthesis §FU-012 specifies the indicator should be at the
    strip's left edge so the user's eye lands on it first when
    glancing at the row. We check by walking the parent layout
    and asserting the state label appears before the speed combo.
    """

    label = window.transport_state_label
    speed_box = window.speed_box
    host = label.parent()
    layout = host.layout()
    state_idx = layout.indexOf(label)
    speed_idx = layout.indexOf(speed_box)
    assert state_idx >= 0
    assert speed_idx >= 0
    assert state_idx < speed_idx, (
        "FU-012 — transport_state_label must appear before "
        "speed_box in the transport strip layout"
    )


# ---------------------------------------------------------------------------
# dark.qss carries the token-grounded rules
# ---------------------------------------------------------------------------


def _read_dark_qss() -> str:
    from pathlib import Path

    return (
        Path(__file__).resolve().parents[2]
        / "src"
        / "chaotic_systems"
        / "gui"
        / "assets"
        / "dark.qss"
    ).read_text(encoding="utf-8")


def test_dark_qss_carries_transport_state_rules() -> None:
    """``dark.qss`` declares the base rule + the two state variants."""

    qss = _read_dark_qss()
    assert 'QLabel[role="transport-state"] {' in qss, (
        "FU-012 — base rule missing"
    )
    assert 'QLabel[role="transport-state"][state="playing"]' in qss, (
        "FU-012 — playing state variant missing"
    )
    assert 'QLabel[role="transport-state"][state="paused"]' in qss, (
        "FU-012 — paused state variant missing"
    )


def test_transport_state_rules_use_palette_tokens() -> None:
    """The three rules use PALETTE colours (text_secondary / accent / accent_pressed)."""

    from chaotic_systems.gui.theme import PALETTE

    qss = _read_dark_qss()
    start = qss.index('QLabel[role="transport-state"] {')
    block = qss[start : start + 2000]
    assert PALETTE.text_secondary in block, (
        f"FU-012 — base 'idle' colour must use PALETTE.text_secondary "
        f"({PALETTE.text_secondary!r}); without this the indicator "
        f"re-introduces the token leak the synthesis flagged."
    )
    assert PALETTE.accent in block, (
        f"FU-012 — 'playing' state must use PALETTE.accent "
        f"({PALETTE.accent!r}) so the indicator reads from across the room"
    )
    assert PALETTE.accent_pressed in block, (
        f"FU-012 — 'paused' state must use PALETTE.accent_pressed "
        f"({PALETTE.accent_pressed!r})"
    )
