"""Tests for the Conradi attractor GUI panel (CSC-007).

GUI tests inherit the ``CHAOTIC_GUI_TESTS_USE_DISPLAY`` gate from
``tests/gui/conftest.py``.

We pin:

- Panel controls exist with stable object names and the documented defaults.
- Construction does not crash and the placeholder canvas renders.
- The worker-finished handler stores the RGBA image, re-enables Render, and
  updates the status label.
- The error handler re-enables Render and surfaces the message.
- A real (small) render flows through the worker's render call and the canvas
  swap without crashing.
- The dialog wraps the panel with the stable object name + attribute.
- The main-window toolbar exposes ``action_conradi`` enabled by default.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


def _make_panel(qtbot):  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.conradi_panel import ConradiPanel

    panel = ConradiPanel()
    qtbot.addWidget(panel)
    return panel


def test_panel_controls_exist(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.a_spin.objectName() == "conradi_a"
    assert panel.b_spin.objectName() == "conradi_b"
    assert panel.n_points_spin.objectName() == "conradi_n_points"
    assert panel.n_iter_spin.objectName() == "conradi_n_iter"
    assert panel.bins_spin.objectName() == "conradi_bins"
    assert panel.cmap_box.objectName() == "conradi_cmap"
    assert panel.tone_box.objectName() == "conradi_tone"
    assert panel.bloom_check.objectName() == "conradi_bloom"
    assert panel.render_button.objectName() == "conradi_render"
    assert panel.progress_bar.objectName() == "conradi_progress"
    assert panel.status_label.objectName() == "conradi_status"
    assert panel.canvas.objectName() == "conradi_canvas"
    # Render starts enabled; progress hidden.
    assert panel.render_button.isEnabled() is True
    assert panel.progress_bar.isVisible() is False or not panel.isVisible()


def test_panel_defaults(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.a_spin.value() == pytest.approx(5.46)
    assert panel.b_spin.value() == pytest.approx(4.55)
    assert panel.cmap_box.currentText() == "magma"
    assert panel.tone_box.currentText() == "log"
    # The colormap picker is populated from the registry.
    from chaotic_systems.visualization import colormaps

    names = [panel.cmap_box.itemText(i) for i in range(panel.cmap_box.count())]
    assert names == colormaps.available()


def test_last_rgba_starts_none(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.last_rgba() is None


def test_finished_handler_stores_rgba_and_updates_status(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel.render_button.setEnabled(False)
    panel.progress_bar.setVisible(True)

    rgba = np.zeros((16, 16, 4), dtype=np.uint8)
    rgba[4:8, 4:8, :3] = 200  # a lit block
    rgba[..., 3] = 255
    panel._on_finished(rgba)  # noqa: SLF001
    assert panel.last_rgba() is rgba
    assert panel.render_button.isEnabled() is True
    assert "16" in panel.status_label.text()
    assert "lit" in panel.status_label.text()


def test_cancelled_finish_does_not_set_rgba(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel._on_finished(None)  # noqa: SLF001
    assert panel.last_rgba() is None
    assert "ancel" in panel.status_label.text().lower()


def test_error_handler_surfaces_message(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel.render_button.setEnabled(False)
    panel._on_error("ValueError", "bad tone")  # noqa: SLF001
    text = panel.status_label.text()
    assert "bad tone" in text
    assert "ValueError" in text
    assert panel.render_button.isEnabled() is True


def test_cleanup_thread_resets_state(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel._worker = MagicMock()  # noqa: SLF001
    panel._thread = MagicMock()  # noqa: SLF001
    panel._cleanup_thread()  # noqa: SLF001
    assert panel._worker is None  # noqa: SLF001
    assert panel._thread is None  # noqa: SLF001


def test_small_render_flows_to_canvas(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A real (small) render reaches the canvas-swap path without crashing."""
    from chaotic_systems.visualization import attractor_density

    panel = _make_panel(qtbot)
    rgba = attractor_density.render(5.46, 4.55, n_points=40, n_iter=40, bins=48)
    panel._on_finished(rgba)  # noqa: SLF001
    assert panel.last_rgba() is not None
    assert panel.canvas.objectName() == "conradi_canvas"


def test_screen_button_exists(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.screen_button.objectName() == "conradi_screen"
    assert panel.last_lle() is None
    assert panel._screen_mode is False  # noqa: SLF001


def test_screen_finished_stores_lle_and_enters_screen_mode(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A real small screening grid flows through to the heatmap + screen mode."""
    from chaotic_systems.visualization import attractor_screen

    panel = _make_panel(qtbot)
    panel.render_button.setEnabled(False)
    panel.screen_button.setEnabled(False)
    lle, _ = attractor_screen.lyapunov_grid(16, n=120, n_transient=40)
    panel._on_screen_finished(lle)  # noqa: SLF001
    assert panel.last_lle() is lle
    assert panel._screen_mode is True  # noqa: SLF001
    assert panel.render_button.isEnabled() is True
    assert panel.screen_button.isEnabled() is True
    assert "chaotic" in panel.status_label.text()


def test_canvas_click_in_screen_mode_sets_ab(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Clicking the heatmap in screen mode sets the a/b spinboxes."""
    from types import SimpleNamespace

    from chaotic_systems.visualization import attractor_screen

    panel = _make_panel(qtbot)
    lle, _ = attractor_screen.lyapunov_grid(16, n=120, n_transient=40)
    panel._on_screen_finished(lle)  # noqa: SLF001 - enter screen mode
    # A fake matplotlib button-press event over the axes.
    event = SimpleNamespace(inaxes=object(), xdata=2.0, ydata=3.0)
    panel._on_canvas_click(event)  # noqa: SLF001
    assert panel.a_spin.value() == pytest.approx(2.0, abs=1e-6)
    assert panel.b_spin.value() == pytest.approx(3.0, abs=1e-6)


def test_canvas_click_ignored_outside_screen_mode(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Clicks do nothing when a density render (not the heatmap) is shown."""
    from types import SimpleNamespace

    panel = _make_panel(qtbot)
    assert panel._screen_mode is False  # noqa: SLF001
    a0, b0 = panel.a_spin.value(), panel.b_spin.value()
    event = SimpleNamespace(inaxes=object(), xdata=1.0, ydata=1.0)
    panel._on_canvas_click(event)  # noqa: SLF001
    assert panel.a_spin.value() == pytest.approx(a0)
    assert panel.b_spin.value() == pytest.approx(b0)


def test_render_after_screen_leaves_screen_mode(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A density render after screening clears screen mode (clicks go inert)."""
    from chaotic_systems.visualization import attractor_density, attractor_screen

    panel = _make_panel(qtbot)
    lle, _ = attractor_screen.lyapunov_grid(16, n=120, n_transient=40)
    panel._on_screen_finished(lle)  # noqa: SLF001
    assert panel._screen_mode is True  # noqa: SLF001
    rgba = attractor_density.render(5.46, 4.55, n_points=40, n_iter=40, bins=48)
    panel._on_finished(rgba)  # noqa: SLF001
    assert panel._screen_mode is False  # noqa: SLF001


def _small_loop():  # type: ignore[no-untyped-def]
    from chaotic_systems.visualization import param_path

    return param_path.precompute_loop_frames(
        4, n_points=40, n_iter=40, bins=48, prescan_frames=2
    )


def test_animation_controls_exist(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.animate_button.objectName() == "conradi_animate"
    assert panel.play_button.objectName() == "conradi_play"
    assert panel.scrubber.objectName() == "conradi_scrub"
    assert panel.play_button.isEnabled() is False
    assert panel.scrubber.isEnabled() is False
    assert panel.last_frames() is None


def test_anim_finished_stores_frames_and_enables_transport(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    payload = _small_loop()
    frames = payload[0]
    panel._on_anim_finished(payload)  # noqa: SLF001
    try:
        assert panel.last_frames() is frames
        assert panel.play_button.isEnabled() is True
        assert panel.scrubber.isEnabled() is True
        assert panel.scrubber.maximum() == len(frames) - 1
        assert "frames" in panel.status_label.text()
    finally:
        panel._stop_play()  # noqa: SLF001


def test_show_frame_updates_index(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel._on_anim_finished(_small_loop())  # noqa: SLF001
    try:
        panel._show_frame(2)  # noqa: SLF001
        assert panel._anim_index == 2  # noqa: SLF001
    finally:
        panel._stop_play()  # noqa: SLF001


def test_play_pause_toggles(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel._on_anim_finished(_small_loop())  # noqa: SLF001
    try:
        assert panel._is_playing is False  # noqa: SLF001
        panel._on_play_pause()  # noqa: SLF001
        assert panel._is_playing is True  # noqa: SLF001
        assert panel.play_button.text() == "Pause"
        panel._on_play_pause()  # noqa: SLF001
        assert panel._is_playing is False  # noqa: SLF001
        assert panel.play_button.text() == "Play"
    finally:
        panel._stop_play()  # noqa: SLF001


def test_scrub_sets_frame_and_pauses(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel._on_anim_finished(_small_loop())  # noqa: SLF001
    panel._start_play()  # noqa: SLF001
    panel._on_scrub(1)  # noqa: SLF001
    assert panel._anim_index == 1  # noqa: SLF001
    assert panel._is_playing is False  # noqa: SLF001


def test_anim_progress_updates_bar(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel._on_anim_progress(2, 4)  # noqa: SLF001
    assert panel.progress_bar.maximum() == 4
    assert panel.progress_bar.value() == 2


def test_render_after_animate_tears_down_transport(qtbot) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.visualization import attractor_density

    panel = _make_panel(qtbot)
    panel._on_anim_finished(_small_loop())  # noqa: SLF001
    assert panel.play_button.isEnabled() is True
    rgba = attractor_density.render(5.46, 4.55, n_points=40, n_iter=40, bins=48)
    panel._on_finished(rgba)  # noqa: SLF001
    assert panel.play_button.isEnabled() is False
    assert panel.scrubber.isEnabled() is False
    assert panel._anim_im is None  # noqa: SLF001


def test_anim_cancelled_finish_keeps_transport_disabled(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel._on_anim_finished(None)  # noqa: SLF001
    assert panel.last_frames() is None
    assert panel.play_button.isEnabled() is False
    assert "ancel" in panel.status_label.text().lower()


def test_export_button_exists_and_starts_disabled(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.export_button.objectName() == "conradi_export"
    assert panel.export_button.isEnabled() is False


def test_export_enabled_after_animate(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel._on_anim_finished(_small_loop())  # noqa: SLF001
    try:
        assert panel.export_button.isEnabled() is True
    finally:
        panel._stop_play()  # noqa: SLF001


def test_export_frames_to_writes_gif(qtbot, tmp_path) -> None:  # type: ignore[no-untyped-def]
    import imageio.v2 as imageio

    panel = _make_panel(qtbot)
    payload = _small_loop()
    panel._on_anim_finished(payload)  # noqa: SLF001
    out = tmp_path / "loop.gif"
    ok = panel._export_frames_to(str(out))  # noqa: SLF001
    assert ok is True
    assert out.exists()
    assert len(imageio.mimread(str(out))) == len(payload[0])
    assert "Saved" in panel.status_label.text()


def test_export_without_frames_returns_false(qtbot, tmp_path) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    ok = panel._export_frames_to(str(tmp_path / "x.gif"))  # noqa: SLF001
    assert ok is False


def test_export_disabled_after_render_teardown(qtbot) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.visualization import attractor_density

    panel = _make_panel(qtbot)
    panel._on_anim_finished(_small_loop())  # noqa: SLF001
    rgba = attractor_density.render(5.46, 4.55, n_points=40, n_iter=40, bins=48)
    panel._on_finished(rgba)  # noqa: SLF001
    assert panel.export_button.isEnabled() is False


def test_dialog_wraps_panel(qtbot) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtWidgets import QWidget

    from chaotic_systems.gui.conradi_panel import build_conradi_dialog

    dialog = build_conradi_dialog()
    qtbot.addWidget(dialog)
    assert dialog.objectName() == "conradi_dialog"
    canvas = dialog.findChild(QWidget, "conradi_canvas")
    assert canvas is not None
    assert dialog.conradi_panel is not None


def test_main_window_exposes_conradi_action(qtbot) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    actions = window.transport_actions()
    assert "action_conradi" in actions
    action = actions["action_conradi"]
    assert action.isEnabled() is True
    assert "Conradi" in action.text() or "conradi" in action.text().lower()


# --- CMP-001: worker forwards map_fn + extent ------------------------------


def test_worker_forwards_clifford_map_and_extent(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The render worker renders a non-Conradi map when given map_fn + extent."""
    import numpy as np

    from chaotic_systems.gui.conradi_panel import _build_worker_class
    from chaotic_systems.systems.clifford import (
        clifford_extent,
        make_clifford_map_fn,
    )

    worker = _build_worker_class()(
        a=-1.4,
        b=1.6,
        n_points=40,
        n_iter=40,
        bins=48,
        tone="log",
        cmap_name="magma",
        bloom=False,
        map_fn=make_clifford_map_fn(1.0, 0.7),
        extent=clifford_extent(1.0, 0.7),
    )
    captured: list[np.ndarray] = []
    worker.finished.connect(captured.append)
    worker.run()  # synchronous emit (no thread) for the test
    assert len(captured) == 1
    rgba = captured[0]
    assert rgba.shape == (48, 48, 4) and rgba.dtype == np.uint8
    lit = np.any(rgba[..., :3] > 0, axis=2)
    assert lit.any() and not lit.all()  # a real figure on a black background


def test_worker_default_map_is_conradi(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Omitting map_fn/extent keeps the Conradi path (byte-stable default)."""
    import numpy as np

    from chaotic_systems.gui.conradi_panel import _build_worker_class
    from chaotic_systems.visualization import attractor_density

    worker = _build_worker_class()(
        a=5.46, b=4.55, n_points=40, n_iter=40, bins=48,
        tone="log", cmap_name="magma", bloom=False,
    )
    captured: list[np.ndarray] = []
    worker.finished.connect(captured.append)
    worker.run()
    assert len(captured) == 1
    expected = attractor_density.render(
        5.46, 4.55, n_points=40, n_iter=40, bins=48,
        tone="log", cmap_name="magma", bloom=False,
    )
    assert np.array_equal(captured[0], expected)


def test_panel_defaults_to_conradi_map(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The panel's active-map seam defaults to the Conradi map + its extent."""
    from chaotic_systems.visualization import attractor_density

    panel = _make_panel(qtbot)
    assert panel._map_fn is attractor_density.conradi_map  # noqa: SLF001
    assert panel._extent == attractor_density.DEFAULT_EXTENT  # noqa: SLF001


# --- CMP-002: map-preset picker UI -----------------------------------------


def test_map_selector_and_per_map_forms_exist(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.map_box.objectName() == "conradi_map_select"
    items = [panel.map_box.itemText(i) for i in range(panel.map_box.count())]
    assert items == ["Conradi", "Clifford"]
    assert panel.map_box.currentText() == "Conradi"
    # Conradi page keeps the original a/b spinboxes (objectNames unchanged).
    assert panel.a_spin.objectName() == "conradi_a"
    assert panel.b_spin.objectName() == "conradi_b"
    # Clifford page has four parameter spinboxes + a preset box.
    assert set(panel.clifford_spins) == {"a", "b", "c", "d"}
    assert panel.clifford_spins["c"].objectName() == "conradi_clifford_c"
    assert panel.conradi_preset_box.objectName() == "conradi_preset"
    assert panel.clifford_preset_box.objectName() == "conradi_clifford_preset"


def test_clifford_spin_ranges_track_map_parameters(qtbot) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.systems.clifford import CliffordMap

    panel = _make_panel(qtbot)
    params = CliffordMap().parameters
    for key in ("a", "b", "c", "d"):
        spin = panel.clifford_spins[key]
        assert spin.minimum() == pytest.approx(params[key].min)
        assert spin.maximum() == pytest.approx(params[key].max)


def test_selecting_clifford_switches_page_and_gates_buttons(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    # Conradi (default): screen + animate enabled.
    assert panel.param_stack.currentIndex() == 0
    assert panel.screen_button.isEnabled() is True
    assert panel.animate_button.isEnabled() is True

    panel.map_box.setCurrentText("Clifford")
    assert panel.param_stack.currentIndex() == 1
    # CMP-004 + CAL-001: screening AND animation are per-map now, so Screen and
    # Animate both work for Clifford too.
    assert panel.screen_button.isEnabled() is True
    assert panel.animate_button.isEnabled() is True

    panel.map_box.setCurrentText("Conradi")
    assert panel.param_stack.currentIndex() == 0
    assert panel.screen_button.isEnabled() is True
    assert panel.animate_button.isEnabled() is True


def test_set_busy_enables_all_compute_buttons_per_map(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel.map_box.setCurrentText("Clifford")
    panel._set_busy(False)  # noqa: SLF001 - idle, Clifford selected
    # CMP-004 (screening) + CAL-001 (animation) work for every map.
    assert panel.render_button.isEnabled() is True
    assert panel.screen_button.isEnabled() is True
    assert panel.animate_button.isEnabled() is True


def test_active_render_spec_per_map(qtbot) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.systems.clifford import clifford_extent
    from chaotic_systems.visualization import attractor_density

    panel = _make_panel(qtbot)
    a, b, map_fn, extent = panel._active_render_spec()  # noqa: SLF001
    assert map_fn is attractor_density.conradi_map
    assert extent == attractor_density.DEFAULT_EXTENT
    assert (a, b) == pytest.approx((panel.a_spin.value(), panel.b_spin.value()))

    panel.map_box.setCurrentText("Clifford")
    panel._on_clifford_preset(0)  # noqa: SLF001 - Bourke I (-1.4,1.6,1.0,0.7)
    a, b, map_fn, extent = panel._active_render_spec()  # noqa: SLF001
    assert (a, b) == pytest.approx((-1.4, 1.6))
    assert extent == clifford_extent(1.0, 0.7)
    assert map_fn is not attractor_density.conradi_map


def test_presets_populate_spinboxes(qtbot) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.systems.clifford import CLIFFORD_PRESETS
    from chaotic_systems.systems.conradi import CONRADI_PRESETS

    panel = _make_panel(qtbot)
    # Conradi preset 1 (the alternate still).
    _label, a, b = CONRADI_PRESETS[1]
    panel._on_conradi_preset(1)  # noqa: SLF001
    assert panel.a_spin.value() == pytest.approx(a)
    assert panel.b_spin.value() == pytest.approx(b)
    # Clifford preset 1.
    _label, ca, cb, cc, cd = CLIFFORD_PRESETS[1]
    panel._on_clifford_preset(1)  # noqa: SLF001
    assert panel.clifford_spins["a"].value() == pytest.approx(ca)
    assert panel.clifford_spins["d"].value() == pytest.approx(cd)


def test_clifford_selection_renders_nontrivial_figure(qtbot) -> None:  # type: ignore[no-untyped-def]
    """End-to-end: the Clifford spec drives a non-trivial render."""
    import numpy as np

    from chaotic_systems.visualization import attractor_density

    panel = _make_panel(qtbot)
    panel.map_box.setCurrentText("Clifford")
    panel._on_clifford_preset(0)  # noqa: SLF001
    a, b, map_fn, extent = panel._active_render_spec()  # noqa: SLF001
    rgba = attractor_density.render(
        a, b, map_fn=map_fn, extent=extent,
        n_points=60, n_iter=60, bins=80, tone="log",
    )
    lit = np.any(rgba[..., :3] > 0, axis=2)
    assert lit.any() and not lit.all()


# --- CMP-004: per-map screening ("Screen (a, b)" for Clifford too) ---------


def test_active_screen_fns_and_range_per_map(qtbot) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.visualization import attractor_screen

    panel = _make_panel(qtbot)
    # Conradi: None/None (lyapunov_grid's built-in default) + [0, 2pi] sweep.
    step, jac = panel._active_screen_fns()  # noqa: SLF001
    assert step is None and jac is None
    a_range, b_range = panel._active_param_range()  # noqa: SLF001
    assert a_range == attractor_screen.SCREEN_A_RANGE

    panel.map_box.setCurrentText("Clifford")
    step, jac = panel._active_screen_fns()  # noqa: SLF001
    assert callable(step) and callable(jac)  # Clifford vectorized pair
    a_range, b_range = panel._active_param_range()  # noqa: SLF001
    assert a_range == (-3.0, 3.0) and b_range == (-3.0, 3.0)


def test_clifford_screen_click_sets_clifford_spins(qtbot) -> None:  # type: ignore[no-untyped-def]
    """In Clifford screen mode, a click writes the Clifford a/b spins (CMP-004)."""
    from types import SimpleNamespace

    import numpy as np

    panel = _make_panel(qtbot)
    panel.map_box.setCurrentText("Clifford")
    # Enter screen mode with a stub LLE field + the Clifford sweep range.
    panel._screen_a_range, panel._screen_b_range = panel._active_param_range()  # noqa: SLF001
    panel._on_screen_finished(np.zeros((8, 8), dtype=np.float64))  # noqa: SLF001
    assert panel._screen_mode is True  # noqa: SLF001
    event = SimpleNamespace(inaxes=object(), xdata=-1.0, ydata=0.5)
    panel._on_canvas_click(event)  # noqa: SLF001
    # Clifford spins updated; the Conradi a_spin is untouched.
    assert panel.clifford_spins["a"].value() == pytest.approx(-1.0)
    assert panel.clifford_spins["b"].value() == pytest.approx(0.5)


def test_clifford_screen_click_clamps_to_range(qtbot) -> None:  # type: ignore[no-untyped-def]
    from types import SimpleNamespace

    import numpy as np

    panel = _make_panel(qtbot)
    panel.map_box.setCurrentText("Clifford")
    panel._screen_a_range, panel._screen_b_range = panel._active_param_range()  # noqa: SLF001
    panel._on_screen_finished(np.zeros((8, 8), dtype=np.float64))  # noqa: SLF001
    # Click far outside the [-3, 3] Clifford range -> clamped.
    event = SimpleNamespace(inaxes=object(), xdata=99.0, ydata=-99.0)
    panel._on_canvas_click(event)  # noqa: SLF001
    assert panel.clifford_spins["a"].value() == pytest.approx(3.0)
    assert panel.clifford_spins["b"].value() == pytest.approx(-3.0)


# --- CAL-001: per-map animation loop geometry ------------------------------


def test_loop_path_fn_selected_per_map(qtbot) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.visualization import param_path

    panel = _make_panel(qtbot)
    # Conradi (default): the default param_loop (None) + wrapped.
    assert panel._loop_path_fn is None  # noqa: SLF001
    assert panel._loop_wrapped is True  # noqa: SLF001

    panel.map_box.setCurrentText("Clifford")
    assert panel._loop_path_fn is param_path.clifford_param_loop  # noqa: SLF001
    assert panel._loop_wrapped is False  # noqa: SLF001

    panel.map_box.setCurrentText("Conradi")
    assert panel._loop_path_fn is None  # noqa: SLF001
    assert panel._loop_wrapped is True  # noqa: SLF001


def test_clifford_animation_precomputes_and_builds_inset(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A Clifford loop animates: frames stored + the (a, b) inset builds."""
    from chaotic_systems.systems.clifford import clifford_extent, make_clifford_map_fn
    from chaotic_systems.visualization import param_path

    panel = _make_panel(qtbot)
    panel.map_box.setCurrentText("Clifford")
    frames, ab, _cmax = param_path.precompute_loop_frames(
        4,
        path_fn=param_path.clifford_param_loop,
        map_fn=make_clifford_map_fn(1.0, 0.7),
        extent=clifford_extent(1.0, 0.7),
        n_points=40,
        n_iter=40,
        bins=48,
        prescan_frames=2,
    )
    panel._on_anim_finished((frames, ab, _cmax))  # noqa: SLF001
    try:
        assert panel.last_frames() is frames
        assert panel.play_button.isEnabled() is True
        assert panel._anim_im is not None  # the in-place AxesImage was built  # noqa: SLF001
    finally:
        panel._stop_play()  # noqa: SLF001
