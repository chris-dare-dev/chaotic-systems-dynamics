"""Theme system for the chaotic-systems GUI.

The GUI ships a coherent dark theme (Tokyo Night Storm palette) and a
placeholder for a light theme. Themes are pure QSS stylesheets shipped
as text files under ``src/chaotic_systems/gui/assets/``; this module
loads them and applies them to a ``QApplication``.

Design tokens — palette, type scale, spacing — are documented in
``docs/ui_design.md``. Keep that doc in sync with the QSS.

Public surface
--------------

- :data:`PALETTE` — the canonical color mapping for the dark theme. The
  Renderer and the LaTeX panel read from this so their output matches
  the surrounding chrome.
- :func:`apply_theme` — install the stylesheet on a ``QApplication``.
- :func:`current_theme` — return the most recently applied theme name.
- :func:`viewport_background` — the color the 3D viewport should clear
  to for the active theme. Used by the renderer wiring in
  ``main_window``.

Why not Qt palettes?
--------------------
``QApplication.setPalette()`` doesn't reach every widget reliably across
styles (in particular on macOS, the native style intercepts many
palette colors). QSS is the more durable approach and matches what
napari, Krita, and other modern Qt apps do.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

__all__ = [
    "PALETTE",
    "Palette",
    "apply_theme",
    "current_theme",
    "viewport_background",
]


@dataclass(frozen=True)
class Palette:
    """The full color set for a theme.

    Hex strings (``#RRGGBB``) — Qt parses these uniformly via
    ``QColor.fromString`` / ``QColor(...)``. The renderer and the LaTeX
    panel both consume these.
    """

    bg_window: str
    bg_panel: str
    bg_elevated: str
    bg_viewport: str
    border: str
    border_strong: str
    text_primary: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_strong: str
    accent_text: str
    success: str
    warning: str
    error: str
    lyapunov: str
    # Derived interaction shades (FU-002 — frontend-uplift 2026-05-19-initial).
    # These are the design-time-derived shades baked into ``assets/dark.qss``
    # for hover / pressed / progress-pill states. Promoting them to PALETTE
    # makes future palette migrations a one-touch change rather than a
    # grep-and-replace across the QSS and ``main_window.py``. The
    # vocabulary mirrors Material Design 3 / Fluent 2 state-token names
    # (``hover``, ``pressed``, ``focus``, ``deep``).
    bg_deep: str
    bg_pill_track: str
    accent_hover: str
    accent_pressed: str
    accent_glow: str


# Tokyo Night Storm palette — kept in lock-step with `assets/dark.qss` and
# `docs/ui_design.md`. Edit all three together.
PALETTE: Final[Palette] = Palette(
    bg_window="#24283b",
    bg_panel="#1f2335",
    bg_elevated="#2a2e42",
    bg_viewport="#16161e",
    border="#3b4261",
    border_strong="#545c7e",
    text_primary="#c0caf5",
    text_secondary="#9aa5ce",
    text_muted="#565f89",
    accent="#7aa2f7",
    accent_strong="#9eb6fb",
    accent_text="#1f2335",
    success="#9ece6a",
    warning="#e0af68",
    error="#f7768e",
    lyapunov="#bb9af7",
    # Derived interaction shades — see Palette dataclass docstring. Each
    # value is anchored to a use site in ``assets/dark.qss`` or
    # ``main_window.py``; if you change one here, update the header
    # comment in ``dark.qss`` so the use sites stay traceable.
    bg_deep="#1a1b26",          # deeper than bg_panel; Notes code blocks, "Deep Night" preset
    bg_pill_track="#2a2c3a",    # pill progress-bar track gradient end-stop
    accent_hover="#343a55",     # secondary button hover; QToolButton hover; spinbox button hover
    accent_pressed="#6788d8",   # primary button pressed; primary toolbutton pressed
    accent_glow="#a4c1ff",      # pill progress chunk gradient highlight stop
)


_ASSETS_DIR: Final[Path] = Path(__file__).resolve().parent / "assets"
_VALID_MODES: Final[frozenset[str]] = frozenset({"dark", "light"})

# Module-level mutable state — ``current_theme()`` reads this. Tests reset
# it via ``apply_theme(..., "dark")`` so the order they run in doesn't
# leak.
_current_theme: str = "dark"


def _stylesheet_path(mode: str) -> Path:
    """Return the QSS file path for ``mode``.

    Falls back to ``dark.qss`` if ``mode == "light"`` and no
    ``light.qss`` has been shipped yet — the light theme is intentionally
    a stub today.
    """

    primary = _ASSETS_DIR / f"{mode}.qss"
    if primary.exists():
        return primary
    return _ASSETS_DIR / "dark.qss"


def apply_theme(app: QApplication, mode: str = "dark") -> None:
    """Install the QSS stylesheet for ``mode`` on ``app``.

    Parameters
    ----------
    app:
        The ``QApplication`` to install the stylesheet on.
    mode:
        Either ``"dark"`` (default) or ``"light"``. Unknown values fall
        back to ``"dark"`` with no error — the QSS is the source of
        truth and we don't want a typo to crash a launch.

    Raises
    ------
    FileNotFoundError
        If neither the requested QSS file nor ``dark.qss`` exists. This
        only happens if the install is broken.
    """

    global _current_theme

    normalized = mode if mode in _VALID_MODES else "dark"
    path = _stylesheet_path(normalized)
    if not path.exists():  # pragma: no cover - install integrity
        raise FileNotFoundError(
            f"theme stylesheet not found: {path}; the install is missing assets/"
        )
    stylesheet = path.read_text(encoding="utf-8")
    # FU-005 — every icon previously loaded via the QSS asset path
    # has been migrated to qtawesome MDI6 glyphs set programmatically
    # (see ``icons.icon_for_stem``); QComboBox / QSpinBox arrows
    # render via Qt-native chevrons. The icon-path-rewriting hack
    # that lived here pre-FU-005 is gone — no asset directory is
    # referenced by the shipped QSS anymore.
    app.setStyleSheet(stylesheet)
    _current_theme = normalized


def current_theme() -> str:
    """Return the most recently applied theme name (``"dark"`` or ``"light"``)."""

    return _current_theme


def viewport_background() -> str:
    """Return the hex color the 3D viewport should clear to.

    The PyVista renderer reads this so its background blends with the
    surrounding chrome instead of fighting it. Dark theme returns the
    near-black viewport background; light theme would return white but
    we keep that wiring on the renderer side.
    """

    if _current_theme == "light":
        return "#ffffff"
    return PALETTE.bg_viewport
