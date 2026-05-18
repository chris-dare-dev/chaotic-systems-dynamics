"""Pin the per-system ``educational_notes`` content shipped with E1.

Each registered system (ODE flow or discrete map) gets a markdown
notes blob that surfaces in the GUI's notes panel. These tests are
the contract: every registered system must ship non-empty notes, and
each blob must cite at least one canonical textbook so the user can
follow up.

We don't validate the prose itself (that's content review, not unit
tests). We do pin:

- ``educational_notes`` exists on both base classes with a string
  default.
- Every registered system supplies a non-empty notes string.
- Each notes string mentions at least one of the canonical textbook
  authors (Strogatz / Ott / Sprott / Lichtenberg / Greene / Chua /
  Hénon / Ikeda / Chirikov / Feigenbaum / May / Rössler / Lorenz /
  Landau / Moon / Guckenheimer / Stankevich / Hammel / Matsumoto /
  Madan / Hairer — the canonical reference set for the systems we
  ship).
"""

from __future__ import annotations

import pytest

from chaotic_systems.core import DiscreteSystem, DynamicalSystem
from chaotic_systems.systems import list_all_systems

# Authors whose names should appear somewhere in at least one
# educational-notes blob across the catalog. Any one match per system
# is enough — the point is that the notes are *grounded in literature*
# rather than free-floating prose.
_CANONICAL_AUTHORS: frozenset[str] = frozenset(
    {
        "Strogatz",
        "Ott",
        "Sprott",
        "Lichtenberg",
        "Greene",
        "Chua",
        "Hénon",
        "Henon",
        "Ikeda",
        "Chirikov",
        "Feigenbaum",
        "May",
        "Rössler",
        "Rossler",
        "Lorenz",
        "Landau",
        "Moon",
        "Guckenheimer",
        "Stankevich",
        "Hammel",
        "Matsumoto",
        "Madan",
        "Hairer",
        "Wolf",
        "Sparrow",
        "Stachowiak",
        "Duffing",
    }
)


def test_base_classes_advertise_educational_notes_attribute() -> None:
    """Both ``DynamicalSystem`` and ``DiscreteSystem`` must declare it."""
    assert hasattr(DynamicalSystem, "educational_notes")
    assert isinstance(DynamicalSystem.educational_notes, str)
    assert hasattr(DiscreteSystem, "educational_notes")
    assert isinstance(DiscreteSystem.educational_notes, str)
    # Defaults are empty strings — that's the "no notes yet" sentinel.
    assert DynamicalSystem.educational_notes == ""
    assert DiscreteSystem.educational_notes == ""


@pytest.mark.parametrize("system", list_all_systems(), ids=lambda s: s.name)
def test_every_registered_system_has_non_empty_notes(system) -> None:  # type: ignore[no-untyped-def]
    """The N1 maps and every continuous flow ship E1 notes."""
    notes = getattr(system, "educational_notes", "")
    assert isinstance(notes, str)
    stripped = notes.strip()
    assert stripped != "", (
        f"{system.name} has empty educational_notes; E1 ships notes for "
        f"every registered system."
    )
    # A minimum-length sanity check — the notes should be a paragraph or
    # two, not a one-line marker. 150 chars is loose enough for a short
    # blurb plus a textbook reference.
    assert len(stripped) >= 150, (
        f"{system.name} has only {len(stripped)} chars of notes; "
        f"too short to carry both a summary and a reference."
    )


@pytest.mark.parametrize("system", list_all_systems(), ids=lambda s: s.name)
def test_notes_cite_at_least_one_canonical_author(system) -> None:  # type: ignore[no-untyped-def]
    """Each system's notes must reference at least one textbook author."""
    notes = getattr(system, "educational_notes", "")
    found = [a for a in _CANONICAL_AUTHORS if a in notes]
    assert found, (
        f"{system.name} notes cite none of the canonical authors "
        f"({sorted(_CANONICAL_AUTHORS)}). Add a Strogatz / Ott / Sprott / "
        f"... reference so users can follow up."
    )


def test_subclass_can_override_notes_without_touching_default() -> None:
    """The default empty string on the base class is preserved when a
    subclass sets its own; pin the dataclass-style override semantics."""

    class _Stub(DiscreteSystem):
        name = "stub"
        latex = ""
        state_dim = 1
        parameters: dict = {}
        educational_notes = "override"

        def _step(self, y, params):  # pragma: no cover - test stub
            return y

    assert _Stub.educational_notes == "override"
    # The base class default is unchanged.
    assert DiscreteSystem.educational_notes == ""
