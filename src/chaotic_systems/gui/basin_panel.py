"""PySide6 panel for the basin-of-attraction explorer (D4).

Embeds a :class:`matplotlib.backends.backend_qtagg.FigureCanvasQTAgg`
inside a Qt widget so the user can:

1. Pick the grid resolution (default 32 × 32 for interactive feel).
2. Set the integration time per orbit.
3. Press Compute and watch a progress pill while a worker thread runs
   one ``solve_ivp`` per grid point.
4. See the basin imshow + attractor markers + legend.

Scope (v1)
----------
The panel ships with the **undriven double-well Duffing** demo
preloaded — two stable fixed points at ``(±1, 0)``, basin boundary
the stable manifold of the saddle at the origin. This is the
canonical pedagogical pairing the proposal calls out (Ott §5.3). The
core ``basin_diagram`` function in :mod:`chaotic_systems.core.basins`
accepts arbitrary scipy- or JAX-callable RHS; future iterations of
this panel can expose system + attractor selection in the UI, but the
v1 ships a single self-contained demo so the worker pattern lands
cleanly.

Worker thread
-------------
:class:`_BasinWorker` runs :func:`~chaotic_systems.core.basins.basin_diagram`
on a :class:`PySide6.QtCore.QThread` and emits ``progress(done, total)``
ticks at ~2% granularity. On completion ``finished(BasinDiagram)``
fires. ``cancel()`` flips an internal flag the worker polls between
grid points so a long sweep can be aborted cleanly without crashing
the GUI.

References
----------
- E. Ott, *Chaos in Dynamical Systems* (2nd ed., 2002), §5.3 — the
  double-well Duffing basin.
- G. Datseris & A. Wagemakers, *Effortless estimation of basins of
  attraction*, Chaos 32 (2022) 023104.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from chaotic_systems.core.basins import (
    BasinDiagram,
    basin_diagram,
    double_well_rhs,
)
from chaotic_systems.visualization.basin_plot import plot_basin

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from PySide6.QtWidgets import QWidget

__all__ = [
    "BasinPanel",  # noqa: F822 - exported lazily via __getattr__ (PySide6 class)
    "build_basin_dialog",
    "build_basin_panel",
]

# Default panel demo: undriven Duffing on (x, v) with the canonical
# double-well attractors at (±1, 0) and the saddle at (0, 0). Range
# spans both wells with some padding so the basin boundary is visible.
_DEMO_X_RANGE: tuple[float, float] = (-2.0, 2.0)
_DEMO_V_RANGE: tuple[float, float] = (-2.0, 2.0)
_DEMO_T_END: float = 50.0
_DEMO_N_GRID: int = 32
# Largest grid the panel allows; 128 x 128 = 16 384 integrations on
# scipy ≈ 80 s on the canonical Duffing, which is the practical
# patience ceiling for an interactive panel. Larger grids should go
# through the library directly with the JAX backend.
_MAX_N_GRID: int = 128


def _build_worker_class() -> type:
    """Build the worker class lazily so PySide6 is only imported on demand."""

    from PySide6.QtCore import QObject, Signal

    class _BasinWorker(QObject):
        """Run :func:`basin_diagram` on a worker thread with progress emission."""

        progress = Signal(int, int)  # (done, total)
        finished = Signal(object)  # BasinDiagram | None on cancel
        error = Signal(str, str)  # (kind, message)

        def __init__(
            self,
            rhs: Any,
            x_axis: tuple[int, float, float],
            y_axis: tuple[int, float, float],
            attractors: list[tuple[str, np.ndarray]],
            fixed_state: np.ndarray,
            n_grid: tuple[int, int],
            t_end: float,
            classify_tol: float,
            system_name: str,
        ) -> None:
            super().__init__()
            self._rhs = rhs
            self._x_axis = x_axis
            self._y_axis = y_axis
            self._attractors = attractors
            self._fixed_state = fixed_state
            self._n_grid = n_grid
            self._t_end = float(t_end)
            self._classify_tol = float(classify_tol)
            self._system_name = system_name
            self._cancelled = False

        def cancel(self) -> None:
            """Mark the sweep as cancelled; the next progress tick will return early."""
            self._cancelled = True

        def run(self) -> None:
            cancel_flag: dict[str, bool] = {"abort": False}

            def _progress(done: int, total: int) -> None:
                if self._cancelled:
                    cancel_flag["abort"] = True
                    # Raise a sentinel exception to break the integration loop.
                    raise _BasinCancelled
                self.progress.emit(done, total)

            try:
                diagram = basin_diagram(
                    self._rhs,
                    x_axis=self._x_axis,
                    y_axis=self._y_axis,
                    attractors=self._attractors,
                    fixed_state=self._fixed_state,
                    n_grid=self._n_grid,
                    t_end=self._t_end,
                    classify_tol=self._classify_tol,
                    backend="scipy",
                    system_name=self._system_name,
                    progress=_progress,
                )
            except _BasinCancelled:
                self.finished.emit(None)
                return
            except (ValueError, KeyError, TypeError) as exc:
                self.error.emit(type(exc).__name__, str(exc))
                return
            except Exception as exc:  # pragma: no cover - last-resort guard
                self.error.emit("Exception", f"{type(exc).__name__}: {exc}")
                return
            self.finished.emit(diagram)

    return _BasinWorker


class _BasinCancelled(Exception):
    """Internal sentinel raised by the worker's progress callback on cancel."""


def _build_panel_class() -> type:
    """Build the BasinPanel class lazily; mirrors the other panel modules."""

    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from PySide6.QtCore import Qt, QThread
    from PySide6.QtWidgets import (
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

    class BasinPanel(QWidget):
        """Self-contained basin-of-attraction explorer for the Duffing demo.

        The demo is the undriven double-well Duffing oscillator (Ott
        §5.3). Two stable fixed points at ``(±1, 0)``; the basin
        boundary is the stable manifold of the saddle at the origin.
        The user can change the grid resolution, integration time,
        and re-run the sweep.
        """

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._worker: object | None = None
            self._thread: QThread | None = None
            self._last_diagram: BasinDiagram | None = None

            outer = QVBoxLayout(self)
            outer.setContentsMargins(8, 8, 8, 8)
            outer.setSpacing(6)

            # --- Controls -------------------------------------------------
            controls = QFormLayout()
            controls.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

            self.n_grid_spin = QSpinBox(self)
            self.n_grid_spin.setObjectName("basin_n_grid")
            self.n_grid_spin.setRange(4, _MAX_N_GRID)
            self.n_grid_spin.setValue(_DEMO_N_GRID)
            self.n_grid_spin.setToolTip(
                "Grid resolution (n × n). 32 ≈ 1 s on scipy; 64 ≈ 15 s; "
                "128 ≈ 80 s. For larger sweeps, use the JAX backend "
                "via the library (see docs/proposals/capability-roadmap-"
                "2026-05-17.md D4)."
            )
            controls.addRow(QLabel("Grid size (n × n)"), self.n_grid_spin)

            self.t_end_spin = QDoubleSpinBox(self)
            self.t_end_spin.setObjectName("basin_t_end")
            self.t_end_spin.setRange(1.0, 500.0)
            self.t_end_spin.setDecimals(1)
            self.t_end_spin.setValue(_DEMO_T_END)
            self.t_end_spin.setSingleStep(5.0)
            self.t_end_spin.setToolTip(
                "Integration time per orbit. Longer = surer convergence "
                "to the asymptotic attractor; ~50 t.u. is enough for "
                "the lightly-damped double-well demo."
            )
            controls.addRow(QLabel("t_end"), self.t_end_spin)

            outer.addLayout(controls)

            # --- Action row -----------------------------------------------
            action_row = QHBoxLayout()
            self.compute_button = QPushButton("Compute basin", self)
            self.compute_button.setObjectName("basin_compute")
            self.compute_button.setProperty("variant", "primary")
            self.compute_button.clicked.connect(self._on_compute)
            action_row.addWidget(self.compute_button)

            self.cancel_button = QPushButton("Cancel", self)
            self.cancel_button.setObjectName("basin_cancel")
            self.cancel_button.setEnabled(False)
            self.cancel_button.clicked.connect(self._on_cancel)
            action_row.addWidget(self.cancel_button)

            self.progress_bar = QProgressBar(self)
            self.progress_bar.setObjectName("basin_progress")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(False)
            action_row.addWidget(self.progress_bar, 1)
            outer.addLayout(action_row)

            # --- Status ---------------------------------------------------
            self.status_label = QLabel(
                "Press Compute to map the undriven double-well Duffing basin.",
                self,
            )
            self.status_label.setObjectName("basin_status")
            self.status_label.setWordWrap(True)
            outer.addWidget(self.status_label)

            # --- Canvas (placeholder until first compute) -----------------
            placeholder = self._placeholder_diagram()
            fig = plot_basin(
                placeholder,
                title="Duffing double-well basins (pending)",
                axes_labels=("x", "v"),
            )
            self.canvas = FigureCanvasQTAgg(fig)
            self.canvas.setObjectName("basin_canvas")
            outer.addWidget(self.canvas, 1)

        # ----- helpers ------------------------------------------------

        def _placeholder_diagram(self) -> BasinDiagram:
            """Build a tiny dummy diagram so the canvas has something to draw."""
            return BasinDiagram(
                x_axis=(0, _DEMO_X_RANGE[0], _DEMO_X_RANGE[1]),
                y_axis=(1, _DEMO_V_RANGE[0], _DEMO_V_RANGE[1]),
                n_grid=(2, 2),
                labels=np.full((2, 2), -1, dtype=np.int64),
                attractor_labels=["left well", "right well"],
                attractor_points=np.array(
                    [[-1.0, 0.0], [1.0, 0.0]], dtype=np.float64
                ),
                fixed_state=np.array([0.0, 0.0], dtype=np.float64),
                system_name="Duffing (double-well)",
                classify_tol=0.5,
                backend="scipy",
            )

        # ----- actions ------------------------------------------------

        def _on_compute(self) -> None:
            if self._thread is not None and self._thread.isRunning():
                return
            n_grid = int(self.n_grid_spin.value())
            t_end = float(self.t_end_spin.value())

            rhs = double_well_rhs()
            attractors: list[tuple[str, np.ndarray]] = [
                ("left well (-1, 0)", np.array([-1.0, 0.0])),
                ("right well (+1, 0)", np.array([1.0, 0.0])),
            ]
            self.compute_button.setEnabled(False)
            self.cancel_button.setEnabled(True)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            self.status_label.setText(
                f"Mapping {n_grid}×{n_grid} = {n_grid * n_grid} initial "
                f"conditions on the undriven Duffing well..."
            )

            worker = worker_cls(
                rhs=rhs,
                x_axis=(0, _DEMO_X_RANGE[0], _DEMO_X_RANGE[1]),
                y_axis=(1, _DEMO_V_RANGE[0], _DEMO_V_RANGE[1]),
                attractors=attractors,
                fixed_state=np.array([0.0, 0.0], dtype=np.float64),
                n_grid=(n_grid, n_grid),
                t_end=t_end,
                # Half-well-width tolerance: ±1 fixed points are well
                # separated, so 0.5 is comfortably inside each well's
                # basin without misclassifying near-boundary orbits
                # whose damping still leaves them ~0.3 from a fixed
                # point at t = t_end.
                classify_tol=0.5,
                system_name="Duffing (double-well)",
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
            self.status_label.setText("Cancelling...")

        def _on_progress(self, done: int, total: int) -> None:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(done)

        def _on_finished(self, diagram: BasinDiagram | None) -> None:
            self.cancel_button.setEnabled(False)
            self.compute_button.setEnabled(True)
            self.progress_bar.setVisible(False)
            if diagram is None:
                self.status_label.setText("Cancelled.")
                return
            self._last_diagram = diagram
            # Headline number: fraction of pixels classified as left vs right.
            n_left = int(np.sum(diagram.labels == 0))
            n_right = int(np.sum(diagram.labels == 1))
            n_unclassified = int(
                np.sum(diagram.labels == -1)
            )
            total = int(diagram.labels.size)
            self.status_label.setText(
                f"Done: {n_left}/{total} left-well, {n_right}/{total} "
                f"right-well, {n_unclassified}/{total} unclassified."
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

        def _refresh_plot(self, diagram: BasinDiagram) -> None:
            """Rebuild the figure and re-bind a Qt canvas."""
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

            fig = plot_basin(
                diagram,
                axes_labels=("x", "v"),
            )
            old = self.canvas
            new_canvas = FigureCanvasQTAgg(fig)
            new_canvas.setObjectName("basin_canvas")
            self.layout().replaceWidget(old, new_canvas)
            old.setParent(None)
            old.deleteLater()
            self.canvas = new_canvas

        # ----- public read-only accessors used by tests ---------------

        def last_diagram(self) -> BasinDiagram | None:
            """Return the most-recently-computed diagram (or ``None``)."""
            return self._last_diagram

    return BasinPanel


def build_basin_panel(parent: QWidget | None = None) -> QWidget:
    """Construct a :class:`BasinPanel` for the bundled Duffing demo."""
    return _build_panel_class()(parent)


def build_basin_dialog(parent: QWidget | None = None) -> QWidget:
    """Build a top-level window wrapping :class:`BasinPanel`."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

    win = QMainWindow(parent)
    win.setObjectName("basin_dialog")
    win.setWindowTitle("Basins of attraction — Duffing double well")
    win.resize(840, 760)
    win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

    central = QWidget(win)
    outer = QVBoxLayout(central)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    panel = build_basin_panel(central)
    outer.addWidget(panel, 1)
    win.setCentralWidget(central)
    win.basin_panel = panel  # type: ignore[attr-defined]
    return win


def __getattr__(name: str) -> type:
    if name == "BasinPanel":
        return _build_panel_class()
    raise AttributeError(name)
