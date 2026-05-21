"""V4 viewport-snapshot tests.

The headline check: writing a PNG of the current PyVista off-screen
plotter actually emits a non-empty PNG header (``\\x89PNG``). The
GUI-side test (``tests/gui/test_export_actions.py``) covers the
action wiring.

Pure-numpy round-trip checks would need to decode the PNG (pulls in
``PIL`` or ``imageio``); since we only care that a real image file
landed, the magic-byte check is enough.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chaotic_systems.visualization.snapshot import save_viewport_png


def _off_screen_plotter():
    pv = pytest.importorskip("pyvista")
    return pv.Plotter(off_screen=True)


def test_save_viewport_png_writes_real_png_file(tmp_path: Path) -> None:
    """End-to-end: an attached off-screen plotter produces a PNG on disk."""
    pytest.importorskip("pyvista")
    plotter = _off_screen_plotter()
    plotter.add_mesh(_make_box())
    dest = save_viewport_png(plotter, tmp_path / "snap.png")
    assert dest.exists()
    assert dest.stat().st_size > 100  # non-empty (PNG has ~67 bytes of overhead minimum)
    # PNG magic number.
    with dest.open("rb") as fh:
        assert fh.read(8) == b"\x89PNG\r\n\x1a\n"


def test_save_viewport_png_with_renderer_object(tmp_path: Path) -> None:
    """Accept a Renderer3D — the helper extracts its ``_plotter`` attr."""
    pytest.importorskip("pyvista")
    import numpy as np

    from chaotic_systems.visualization.renderer import Renderer3D

    # Build a tiny trajectory + renderer attached to an off-screen plotter.
    t = np.linspace(0.0, 1.0, 30)
    pts = np.column_stack([np.sin(t), np.cos(t), t])
    renderer = Renderer3D(pts)
    plotter = _off_screen_plotter()
    renderer._plotter = plotter  # noqa: SLF001
    renderer._build_scene(plotter)  # noqa: SLF001

    dest = save_viewport_png(renderer, tmp_path / "renderer.png")
    assert dest.exists()
    with dest.open("rb") as fh:
        assert fh.read(8) == b"\x89PNG\r\n\x1a\n"


def test_save_viewport_png_explicit_size(tmp_path: Path) -> None:
    """Custom ``size`` is forwarded to plotter.screenshot's window_size."""
    pytest.importorskip("pyvista")
    plotter = _off_screen_plotter()
    plotter.add_mesh(_make_box())
    dest = save_viewport_png(
        plotter, tmp_path / "wide.png", size=(640, 200)
    )
    assert dest.exists()


def test_save_viewport_png_rejects_renderer_without_plotter(tmp_path: Path) -> None:
    """A Renderer3D that was never attached has no plotter — must raise
    a clean RuntimeError, not a cryptic AttributeError."""
    import numpy as np

    from chaotic_systems.visualization.renderer import Renderer3D

    renderer = Renderer3D(np.column_stack([[0.0, 1.0], [0.0, 1.0], [0.0, 1.0]]))
    # ``_plotter`` is None on a fresh instance.
    with pytest.raises(RuntimeError, match="no attached plotter"):
        save_viewport_png(renderer, tmp_path / "nope.png")


def _make_box():
    """Tiny PyVista mesh so screenshots aren't blank."""
    import pyvista as pv

    return pv.Box()
