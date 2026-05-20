"""PySide6 panel for the bifurcation-diagram tool.

Embeds a :class:`matplotlib.backends.backend_qtagg.FigureCanvasQTAgg`
inside a Qt widget so the user can:

1. Pick which parameter of the selected discrete map to sweep.
2. Set the sweep range (min, max) and resolution (number of values).
3. Press Compute and watch a progress pill while a worker thread
   iterates the map ``n_values × (n_transient + n_record)`` times.
4. See the resulting Feigenbaum-style scatter rendered in-panel.

The panel is intentionally **stand-alone** — it does not assume a
parent main window and is constructible in isolation against any
:class:`~chaotic_systems.core.DiscreteSystem`. The main window wires
it into a top-level dialog opened from a Diagnostics-card button
(see :mod:`chaotic_systems.gui.main_window`).

Worker thread
-------------
Compute happens on a :class:`PySide6.QtCore.QThread` driven by
:class:`_BifurcationWorker`. The worker iterates over the parameter
values one at a time so it can emit progress ticks ~10× per sweep
(coarser ticks would feel unresponsive; finer ticks would stall on
the GIL during the iterate loop). On finish it emits the full
:class:`BifurcationDiagram`; the panel then re-binds a Qt canvas to
the Agg-built figure and refreshes the view.

Cancellation is a per-tick check on a single ``_cancelled`` flag —
when set, the worker emits ``finished(None)`` so the panel can re-
enable the Compute button without surfacing an error dialog.

References
----------
- Sales et al., *pynamicalsys*, Chaos, Solitons & Fractals 201 (2025) —
  the 2025 reference implementation; this panel exposes the same
  controls (parameter, range, ``n_values``, ``n_transient``,
  ``n_record``) on a Qt surface.
- May 1976 / Strogatz §10.6 for the canonical figure this reproduces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from chaotic_systems.core.bifurcation import (
    DEFAULT_N_RECORD,
    DEFAULT_N_TRANSIENT,
    DEFAULT_N_VALUES,
    BifurcationDiagram,
)
from chaotic_systems.core.discrete import DiscreteSystem
from chaotic_systems.visualization.bifurcation_plot import plot_bifurcation

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from PySide6.QtWidgets import QWidget

__all__ = [
    "BifurcationPanel",  # noqa: F822 - exported lazily via __getattr__ (PySide6 class)
    "build_bifurcation_dialog",
    "build_bifurcation_panel",
]


# Wall-clock guard: emit at most this many progress ticks per sweep
# (coarser = lighter GUI load, finer = more responsive cancel). 50
# ticks is one tick per ~2% of the sweep, which feels live on screens
# refreshing at 60 Hz.
_PROGRESS_TICKS: int = 50


def _build_worker_class() -> type:
    """Build the worker class lazily so PySide6 is only imported on demand.

    Same pattern as :func:`chaotic_systems.gui.main_window._build_window_class`
    — the GUI panel is constructible without paying the PySide6 import
    cost at module-import time, which keeps test collection fast.
    """

    from PySide6.QtCore import QObject, Signal

    class _BifurcationWorker(QObject):
        """Run :func:`bifurcation_diagram` on a worker thread.

        Iterates the sweep one parameter value at a time, emitting a
        ``progress(done, total)`` tick at ~2% granularity so the GUI
        can drive a determinate progress bar.

        On completion ``finished(BifurcationDiagram)`` fires. On
        cancellation ``finished(None)`` fires so the panel can clean
        up without surfacing an error. Hard errors emit
        ``error(kind, message)``.
        """

        progress = Signal(int, int)  # (done, total)
        finished = Signal(object)  # BifurcationDiagram | None
        error = Signal(str, str)  # (kind, message)

        def __init__(
            self,
            system: DiscreteSystem,
            param_name: str,
            param_values: np.ndarray,
            n_record: int = DEFAULT_N_RECORD,
            n_transient: int = DEFAULT_N_TRANSIENT,
            fixed_params: dict[str, float] | None = None,
        ) -> None:
            super().__init__()
            self._system = system
            self._param_name = param_name
            self._param_values = np.ascontiguousarray(param_values, dtype=np.float64)
            self._n_record = int(n_record)
            self._n_transient = int(n_transient)
            self._fixed_params = dict(fixed_params or {})
            self._cancelled = False

        def cancel(self) -> None:
            """Mark the sweep as cancelled; the next tick will return early."""
            self._cancelled = True

        def run(self) -> None:
            try:
                m = int(self._param_values.shape[0])
                samples = np.empty(
                    (m, self._n_record, self._system.state_dim), dtype=np.float64
                )
                base_params = dict(self._system.default_params())
                for k, v in self._fixed_params.items():
                    if k in base_params:
                        base_params[k] = float(v)
                tick_every = max(1, m // _PROGRESS_TICKS)
                seed = self._system.initial_state
                for i in range(m):
                    if self._cancelled:
                        self.finished.emit(None)
                        return
                    params = dict(base_params)
                    params[self._param_name] = float(self._param_values[i])
                    traj = self._system.iterate(
                        n_steps=self._n_record,
                        y0=seed,
                        params=params,
                        n_transient=self._n_transient,
                    )
                    samples[i] = traj.y[1:]
                    if (i + 1) % tick_every == 0 or i == m - 1:
                        self.progress.emit(i + 1, m)
                diagram = BifurcationDiagram(
                    system_name=self._system.name,
                    param_name=self._param_name,
                    param_values=self._param_values,
                    samples=samples,
                    state_dim=self._system.state_dim,
                    fixed_params=base_params,
                )
                self.finished.emit(diagram)
            except (KeyError, ValueError, TypeError) as exc:
                self.error.emit(type(exc).__name__, str(exc))
            except Exception as exc:  # pragma: no cover - last-resort guard
                self.error.emit("Exception", f"{type(exc).__name__}: {exc}")

    return _BifurcationWorker


def _build_panel_class() -> type:
    """Build the BifurcationPanel class lazily; see :func:`_build_worker_class`."""

    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from PySide6.QtCore import Qt, QThread
    from PySide6.QtWidgets import (
        QComboBox,
        QDoubleSpinBox,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QProgressBar,
        QPushButton,
        QSpinBox,
        QVBoxLayout,
        QWidget,
    )

    worker_cls = _build_worker_class()

    class BifurcationPanel(QWidget):
        """A self-contained bifurcation-diagram explorer.

        Construct against any :class:`DiscreteSystem`. The widget owns
        the matplotlib figure / canvas and the worker thread; opening
        it in a top-level dialog is enough to give the user a fully
        functional explorer.
        """

        def __init__(
            self,
            system: DiscreteSystem,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            if not isinstance(system, DiscreteSystem):
                raise TypeError(
                    "BifurcationPanel currently supports DiscreteSystem only; "
                    f"got {type(system).__name__}."
                )
            self._system = system
            self._worker: object | None = None
            self._thread: QThread | None = None
            self._last_diagram: BifurcationDiagram | None = None

            from chaotic_systems.gui._panel_helpers import apply_panel_margins

            outer = QVBoxLayout(self)
            apply_panel_margins(outer)

            # --- Controls row -----------------------------------------
            controls = QFormLayout()
            controls.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

            self.param_box = QComboBox(self)
            self.param_box.setObjectName("bifurcation_param_box")
            for name in system.parameters:
                self.param_box.addItem(name)
            controls.addRow(QLabel("Parameter"), self.param_box)

            self.min_spin = QDoubleSpinBox(self)
            self.min_spin.setObjectName("bifurcation_min")
            self.min_spin.setDecimals(6)
            self.min_spin.setRange(-1e9, 1e9)
            self.max_spin = QDoubleSpinBox(self)
            self.max_spin.setObjectName("bifurcation_max")
            self.max_spin.setDecimals(6)
            self.max_spin.setRange(-1e9, 1e9)
            range_row = QHBoxLayout()
            range_row.addWidget(self.min_spin)
            range_row.addWidget(QLabel("→"))
            range_row.addWidget(self.max_spin)
            range_wrap = QWidget(self)
            range_wrap.setLayout(range_row)
            controls.addRow(QLabel("Range"), range_wrap)

            self.n_values_spin = QSpinBox(self)
            self.n_values_spin.setObjectName("bifurcation_n_values")
            self.n_values_spin.setRange(2, 100_000)
            self.n_values_spin.setValue(DEFAULT_N_VALUES)
            controls.addRow(QLabel("# values"), self.n_values_spin)

            self.n_transient_spin = QSpinBox(self)
            self.n_transient_spin.setObjectName("bifurcation_n_transient")
            self.n_transient_spin.setRange(0, 1_000_000)
            self.n_transient_spin.setValue(DEFAULT_N_TRANSIENT)
            controls.addRow(QLabel("Transient"), self.n_transient_spin)

            self.n_record_spin = QSpinBox(self)
            self.n_record_spin.setObjectName("bifurcation_n_record")
            self.n_record_spin.setRange(1, 100_000)
            self.n_record_spin.setValue(DEFAULT_N_RECORD)
            controls.addRow(QLabel("Record"), self.n_record_spin)

            self.projection_spin = QSpinBox(self)
            self.projection_spin.setObjectName("bifurcation_projection")
            self.projection_spin.setRange(0, max(0, system.state_dim - 1))
            self.projection_spin.setValue(0)
            self.projection_spin.setEnabled(system.state_dim > 1)
            controls.addRow(QLabel("y-axis = y["), self.projection_spin)

            outer.addLayout(controls)

            # --- Action row -------------------------------------------
            action_row = QHBoxLayout()
            self.compute_button = QPushButton("Compute bifurcation diagram", self)
            self.compute_button.setObjectName("bifurcation_compute")
            self.compute_button.setProperty("variant", "primary")
            self.compute_button.clicked.connect(self._on_compute)
            action_row.addWidget(self.compute_button)

            self.cancel_button = QPushButton("Cancel", self)
            self.cancel_button.setObjectName("bifurcation_cancel")
            self.cancel_button.setEnabled(False)
            self.cancel_button.clicked.connect(self._on_cancel)
            action_row.addWidget(self.cancel_button)

            self.progress_bar = QProgressBar(self)
            self.progress_bar.setObjectName("bifurcation_progress")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(False)
            action_row.addWidget(self.progress_bar, 1)
            outer.addLayout(action_row)

            # --- Status label -----------------------------------------
            self.status_label = QLabel("", self)
            self.status_label.setObjectName("bifurcation_status")
            self.status_label.setWordWrap(True)
            outer.addWidget(self.status_label)

            # --- Plot canvas ------------------------------------------
            # Build an initial placeholder figure so the canvas has a
            # surface to draw before the first sweep finishes.
            fig = plot_bifurcation(
                self._empty_diagram(),
                title=f"{system.name} bifurcation diagram (pending)",
            )
            self.canvas = FigureCanvasQTAgg(fig)
            self.canvas.setObjectName("bifurcation_canvas")
            outer.addWidget(self.canvas, 1)

            # Seed parameter-range fields with the swept parameter's [min, max].
            self.param_box.currentTextChanged.connect(self._on_param_changed)
            self._on_param_changed(self.param_box.currentText())

        # ----- helpers -----------------------------------------------

        def _empty_diagram(self) -> BifurcationDiagram:
            """Build a single-value diagram so the placeholder canvas renders."""
            param_name = next(iter(self._system.parameters))
            return BifurcationDiagram(
                system_name=self._system.name,
                param_name=param_name,
                param_values=np.array(
                    [self._system.parameters[param_name].default],
                    dtype=np.float64,
                ),
                samples=np.zeros((1, 1, self._system.state_dim), dtype=np.float64),
                state_dim=self._system.state_dim,
                fixed_params=dict(self._system.default_params()),
            )

        def _on_param_changed(self, name: str) -> None:
            param = self._system.parameters.get(name)
            if param is None:
                return
            # Seed the range spinboxes with the parameter's declared bounds —
            # that's the most useful default for "I want to see the full
            # bifurcation picture of this parameter".
            self.min_spin.setRange(-1e9, 1e9)
            self.max_spin.setRange(-1e9, 1e9)
            self.min_spin.setValue(float(param.min))
            self.max_spin.setValue(float(param.max))

        # ----- actions ----------------------------------------------

        def _on_compute(self) -> None:
            if self._thread is not None and self._thread.isRunning():
                return
            param_name = self.param_box.currentText()
            lo = float(self.min_spin.value())
            hi = float(self.max_spin.value())
            n_values = int(self.n_values_spin.value())
            n_transient = int(self.n_transient_spin.value())
            n_record = int(self.n_record_spin.value())
            if not lo < hi:
                self.status_label.setText("Range min must be strictly less than max.")
                return
            try:
                param_values = np.linspace(lo, hi, n_values)
            except (ValueError, OverflowError) as exc:
                self.status_label.setText(f"Range error: {exc}")
                return

            self.compute_button.setEnabled(False)
            self.cancel_button.setEnabled(True)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            self.status_label.setText(
                f"Sweeping {param_name} over {n_values} values…"
            )

            worker = worker_cls(
                self._system,
                param_name,
                param_values,
                n_record=n_record,
                n_transient=n_transient,
            )
            thread = QThread(self)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.progress.connect(self._on_progress)
            worker.finished.connect(self._on_finished)
            worker.error.connect(self._on_error)
            worker.finished.connect(thread.quit)
            worker.error.connect(thread.quit)
            thread.finished.connect(self._cleanup_thread)
            self._worker = worker
            self._thread = thread
            thread.start()

        def _on_cancel(self) -> None:
            if self._worker is not None:
                self._worker.cancel()  # type: ignore[attr-defined]
            self.status_label.setText("Cancelling…")

        def _on_progress(self, done: int, total: int) -> None:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(done)

        def _on_finished(self, diagram: BifurcationDiagram | None) -> None:
            self.cancel_button.setEnabled(False)
            self.compute_button.setEnabled(True)
            self.progress_bar.setVisible(False)
            if diagram is None:
                self.status_label.setText("Cancelled.")
                return
            self._last_diagram = diagram
            self.status_label.setText(
                f"Done: {diagram.n_values} values × {diagram.n_record} iterates."
            )
            self._refresh_plot(diagram)

        def _on_error(self, kind: str, message: str) -> None:
            self.cancel_button.setEnabled(False)
            self.compute_button.setEnabled(True)
            self.progress_bar.setVisible(False)
            self.status_label.setText(f"{kind}: {message}")

        def _cleanup_thread(self) -> None:
            if self._worker is not None:
                self._worker.deleteLater()  # type: ignore[attr-defined]
            if self._thread is not None:
                self._thread.deleteLater()
            self._worker = None
            self._thread = None

        def _refresh_plot(self, diagram: BifurcationDiagram) -> None:
            """Rebuild the figure and re-bind a Qt canvas."""
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

            from chaotic_systems.gui._panel_helpers import swap_mpl_canvas

            projection = int(self.projection_spin.value())
            fig = plot_bifurcation(diagram, projection=projection)
            new_canvas = FigureCanvasQTAgg(fig)
            new_canvas.setObjectName("bifurcation_canvas")
            swap_mpl_canvas(self.layout(), self.canvas, new_canvas)
            self.canvas = new_canvas

        # ----- public read-only accessors used by tests ---------------

        def last_diagram(self) -> BifurcationDiagram | None:
            """Return the most-recently-computed diagram (or ``None``)."""
            return self._last_diagram

    return BifurcationPanel


def build_bifurcation_panel(
    system: DiscreteSystem,
    parent: QWidget | None = None,
) -> QWidget:
    """Construct a :class:`BifurcationPanel` for ``system``.

    Convenience constructor that wraps the lazy-built class so callers
    don't have to know about ``_build_panel_class``.
    """
    return _build_panel_class()(system, parent)


def build_bifurcation_dialog(
    maps: list[DiscreteSystem] | None = None,
    parent: QWidget | None = None,
) -> QWidget:
    """Build a self-contained top-level window: map picker + BifurcationPanel.

    This is what the main-window toolbar action opens — it bundles a
    combobox over the registered maps (or the supplied ``maps`` list)
    with a :class:`BifurcationPanel` that swaps when the user picks a
    different map. The dialog owns its lifetime; show it with
    ``.show()`` and let Qt's normal close behaviour clean it up.
    """
    from PySide6.QtWidgets import (
        QComboBox,
        QHBoxLayout,
        QLabel,
        QVBoxLayout,
        QWidget,
    )

    from chaotic_systems.gui._panel_helpers import (
        apply_panel_margins,
        make_panel_dialog,
    )

    panel_cls = _build_panel_class()

    if maps is None:
        from chaotic_systems.systems.registry import list_maps as _list_maps

        maps_list = list(_list_maps())
    else:
        maps_list = list(maps)
    if not maps_list:
        raise ValueError(
            "build_bifurcation_dialog: no discrete maps available; "
            "the registry returned an empty list."
        )

    # FU-018 — dock widget so the user can dock the Bifurcation
    # explorer beside the viewport. The widget container that used
    # to be the QMainWindow's centralWidget becomes the dock's
    # single ``setWidget`` payload.
    central = QWidget(parent)
    outer = QVBoxLayout(central)
    # FU-022 — outer panel uses the canonical 8/8 panel margin but
    # overrides spacing to 8 because the map-picker row sits flush
    # against the panel host (the rest of the panels have a single
    # vertical run and use the default 6).
    apply_panel_margins(outer, spacing=8)

    picker_row = QHBoxLayout()
    picker_row.addWidget(QLabel("Map", central))
    picker_box = QComboBox(central)
    picker_box.setObjectName("bifurcation_map_picker")
    for m in maps_list:
        picker_box.addItem(m.name)
    picker_row.addWidget(picker_box, 1)
    outer.addLayout(picker_row)

    # Container the panel lives in; we swap its child when the picker changes.
    panel_host = QWidget(central)
    panel_host.setObjectName("bifurcation_panel_host")
    panel_layout = QVBoxLayout(panel_host)
    apply_panel_margins(panel_layout, margin=0, spacing=0)
    outer.addWidget(panel_host, 1)

    current_panel: dict[str, QWidget | None] = {"panel": None}

    def _swap(idx: int) -> None:
        if not 0 <= idx < len(maps_list):
            return
        if current_panel["panel"] is not None:
            old = current_panel["panel"]
            panel_layout.removeWidget(old)
            old.setParent(None)
            old.deleteLater()
        new_panel = panel_cls(maps_list[idx], panel_host)
        panel_layout.addWidget(new_panel)
        current_panel["panel"] = new_panel

    picker_box.currentIndexChanged.connect(_swap)
    _swap(0)

    dock = make_panel_dialog(
        object_name="bifurcation_dialog",
        title="Bifurcation diagram",
        panel=central,
        size=(900, 700),
        parent=parent,
    )
    # Expose the picker so callers (tests, future scripts) can drive it.
    # The bifurcation dialog uses ``.map_picker`` instead of the
    # canonical ``.<name>_panel`` because the dialog hosts a
    # map-picker combobox + swappable BifurcationPanel internally
    # — the tests + command palette consume the picker, not the
    # inner panel.
    dock.map_picker = picker_box  # type: ignore[attr-defined]
    return dock


# Module-level lazy alias: ``BifurcationPanel`` resolves to the
# PySide6-built class on first access. Mirrors the pattern used by
# :mod:`chaotic_systems.gui.main_window`.
def __getattr__(name: str) -> type:
    if name == "BifurcationPanel":
        return _build_panel_class()
    raise AttributeError(name)
