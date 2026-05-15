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
    # Resolve asset URLs against the installed package so QSS works under
    # editable installs, wheels, and zip-imported packages alike. Tokens of
    # the form ``url(assets/icons/foo.svg)`` are rewritten to absolute
    # ``file:///...`` URLs; the QSS files use the relative form so they
    # stay readable when viewed standalone.
    icons_dir = _ASSETS_DIR / "icons"
    if icons_dir.exists():
        # Qt resolves QSS ``url(...)`` against the application working
        # directory, so we substitute the absolute filesystem path.
        # ``file://`` URIs would be cleaner but Qt 6's QSS parser strips
        # the scheme inconsistently across platforms — bare absolute
        # paths Just Work.
        stylesheet = stylesheet.replace(
            "url(assets/icons/",
            f"url({icons_dir.as_posix()}/",
        )
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
