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

Why Fusion + a palette *and* QSS?
---------------------------------
``QApplication.setPalette()`` doesn't reach every widget reliably under
the platform *native* styles: on macOS the native style intercepts many
palette colors, and on Windows ``windows11`` / ``windowsvista`` ignores
large parts of a stylesheet and falls back to the light *system* palette
for native-drawn subcontrols (combobox drop-downs, spinbox buttons) and
for unstyled container backgrounds. That divergence is what made the GUI
look correct on macOS but render white/grey panel-title blocks and a
mis-placed attractor dropdown on Windows. The fix is to pin the
**Fusion** style — the one built-in style that honours a stylesheet
*and* a palette uniformly on every OS — and back it with a dark palette
derived from :data:`PALETTE`. The QSS then paints the detailed chrome on
top while the palette fills anything the QSS leaves unstyled, keeping the
window identical across platforms. See :func:`apply_theme`.
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


def _apply_base_style(app: QApplication) -> None:
    """Pin the Fusion style + a dark ``QPalette`` so the QSS renders the
    same on every platform.

    Qt's *native* styles only partially honour stylesheets and fall back
    to the light *system* palette for native-drawn subcontrols (combobox
    drop-downs, spinbox buttons) and for unstyled container backgrounds.
    macOS's native style cooperated with our QSS; Windows'
    ``windows11`` / ``windowsvista`` did not, producing white/grey
    panel-title blocks and a mis-placed attractor dropdown. Fusion is the
    only built-in style that respects a stylesheet *and* a palette
    uniformly across platforms, so we pin it everywhere and back it with
    a palette derived from :data:`PALETTE`. Qt imports are local so this
    module stays importable without a running ``QApplication``.
    """

    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QStyleFactory

    fusion = QStyleFactory.create("Fusion")
    if fusion is not None:  # pragma: no branch - Fusion always ships with Qt
        app.setStyle(fusion)

    p = PALETTE
    role = QPalette.ColorRole
    palette = QPalette()
    palette.setColor(role.Window, QColor(p.bg_window))
    palette.setColor(role.WindowText, QColor(p.text_primary))
    palette.setColor(role.Base, QColor(p.bg_panel))
    palette.setColor(role.AlternateBase, QColor(p.bg_elevated))
    palette.setColor(role.Text, QColor(p.text_primary))
    palette.setColor(role.Button, QColor(p.bg_elevated))
    palette.setColor(role.ButtonText, QColor(p.text_primary))
    palette.setColor(role.BrightText, QColor(p.error))
    palette.setColor(role.ToolTipBase, QColor(p.bg_elevated))
    palette.setColor(role.ToolTipText, QColor(p.text_primary))
    palette.setColor(role.PlaceholderText, QColor(p.text_muted))
    palette.setColor(role.Highlight, QColor(p.accent))
    palette.setColor(role.HighlightedText, QColor(p.accent_text))
    palette.setColor(role.Link, QColor(p.accent))
    palette.setColor(role.LinkVisited, QColor(p.accent_strong))

    disabled = QPalette.ColorGroup.Disabled
    palette.setColor(disabled, role.WindowText, QColor(p.text_muted))
    palette.setColor(disabled, role.Text, QColor(p.text_muted))
    palette.setColor(disabled, role.ButtonText, QColor(p.text_muted))

    app.setPalette(palette)


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
    # FU-005 migrated toolbar/button icons to qtawesome MDI6 glyphs set
    # programmatically (see ``icons.icon_for_stem``). It also dropped the
    # combobox/spinbox arrow images on the assumption that Qt would draw a
    # *native* chevron — but once the QSS styles ``::drop-down`` /
    # ``::up-button``, the Qt Style Sheet engine owns the whole control and
    # paints NOTHING for an arrow subcontrol with no ``image:``, so the
    # pickers rendered arrow-less on Windows. FU-PATCH (2026-06-03) ships
    # explicit chevron SVGs again, referenced via the ``__ASSETS__`` token
    # below. Qt resolves a bare ``url(...)`` in a stylesheet against the
    # process CWD rather than the QSS file, so we rewrite the token to the
    # absolute ``assets/`` path here (a minimal revival of the pre-FU-005
    # path-injection, scoped to the two chevron glyphs).
    stylesheet = stylesheet.replace("__ASSETS__", _ASSETS_DIR.as_posix())
    #
    # Cross-platform parity: pin Fusion + a dark palette *before* the
    # stylesheet so native styles (notably Windows ``windows11``) can't
    # leak the light system palette into combobox drop-downs, spinbox
    # buttons or unstyled container backgrounds. Without this the dark
    # QSS rendered correctly on macOS but showed white/grey panel-title
    # blocks and a mis-placed attractor dropdown on Windows.
    _apply_base_style(app)
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
