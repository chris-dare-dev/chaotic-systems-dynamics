"""PySide6 panel for the 2D phase-portrait tool.

Embeds a :class:`matplotlib.backends.backend_qtagg.FigureCanvasQTAgg`
inside a Qt widget so the user can pick any two state-vector indices
and see the corresponding 2D projection of the current trajectory.

The panel is **read-only against a single trajectory snapshot** — the
main window passes in the most recent simulation result and the panel
re-plots when the user changes the axis combos. To refresh against a
newer simulation, the user closes the panel and re-opens it; this
keeps the panel free of cross-thread bookkeeping (no QThread worker
needed, because re-plotting a few-thousand-point trajectory is well
under one screen frame).

The companion module :mod:`chaotic_systems.visualization.phase_plot`
is the pure-matplotlib side; see also
:mod:`chaotic_systems.gui.bifurcation_panel` for the closely-related
pattern (FigureCanvasQTAgg + lazy class build + Tokyo-Night-aware
facecolor).

References
----------
- S. Strogatz, *Nonlinear Dynamics and Chaos* (2nd ed., 2015), §6.1
  "Phase Portraits" — every figure in the chapter is reproducible
  here by picking two state indices and clicking Plot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from chaotic_systems.visualization.phase_plot import plot_phase_portrait

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from PySide6.QtWidgets import QWidget

__all__ = [
    "PhasePanel",  # noqa: F822 - exported lazily via __getattr__ (PySide6 class)
    "build_phase_dialog",
    "build_phase_panel",
]


def _trajectory_state_dim(trajectory: Any) -> int:
    """Best-effort: read ``trajectory.state_dim`` or infer from ``.y``."""
    sd = getattr(trajectory, "state_dim", None)
    if sd is not None:
        return int(sd)
    y = getattr(trajectory, "y", None)
    if y is None:
        raise TypeError(
            "phase-panel input must carry .state_dim or .y; got "
            f"{type(trajectory).__name__}"
        )
    arr = getattr(y, "shape", None)
    if arr is None or len(arr) != 2:
        raise TypeError(
            "phase-panel input .y must be 2-D; got shape "
            f"{getattr(y, 'shape', None)!r}"
        )
    # Heuristic mirroring chaotic_systems.visualization.contract: the
    # shorter axis is state_dim when (N, state_dim) is ambiguous.
    return int(min(arr))


def _build_panel_class() -> type:
    """Build the :class:`PhasePanel` class lazily; mirrors the bifurcation
    panel pattern so PySide6 is only imported on first construction."""

    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    class PhasePanel(QWidget):
        """A self-contained 2D phase-portrait explorer for one trajectory.

        Construct against a :class:`~chaotic_systems.core.Trajectory`
        (or any duck-typed object with ``.y`` and ``.state_dim``). The
        widget owns the matplotlib figure and canvas; opening it in a
        top-level dialog is enough to give the user a fully functional
        explorer for that snapshot.
        """

        def __init__(
            self,
            trajectory: Any,
            *,
            axes_labels: tuple[str, ...] | None = None,
            system_name: str | None = None,
            facecolor: str | None = None,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self._trajectory = trajectory
            self._axes_labels = axes_labels
            self._facecolor = facecolor
            self._state_dim = _trajectory_state_dim(trajectory)
            if self._state_dim < 2:
                raise ValueError(
                    "PhasePanel requires a trajectory with state_dim >= 2; "
                    f"got state_dim={self._state_dim}"
                )
            # Derive a display title from the trajectory's system name or
            # the explicit override.
            self._system_name = (
                system_name
                if system_name is not None
                else str(getattr(trajectory, "system", "") or "trajectory")
            )

            outer = QVBoxLayout(self)
            outer.setContentsMargins(8, 8, 8, 8)
            outer.setSpacing(6)

            # --- Axis pickers + plot button -----------------------------------
            controls = QFormLayout()
            controls.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

            def _build_axis_combo(name: str, default: int) -> QComboBox:
                combo = QComboBox(self)
                combo.setObjectName(name)
                for i in range(self._state_dim):
                    label = (
                        axes_labels[i]
                        if axes_labels is not None and i < len(axes_labels)
                        else f"y[{i}]"
                    )
                    combo.addItem(f"{i}: {label}", userData=i)
                combo.setCurrentIndex(default)
                return combo

            self.x_axis_box = _build_axis_combo("phase_x_axis", 0)
            self.y_axis_box = _build_axis_combo(
                "phase_y_axis", 1 if self._state_dim > 1 else 0
            )
            controls.addRow(QLabel("X axis"), self.x_axis_box)
            controls.addRow(QLabel("Y axis"), self.y_axis_box)

            self.equal_aspect_box = QCheckBox("Equal aspect", self)
            self.equal_aspect_box.setObjectName("phase_equal_aspect")
            self.equal_aspect_box.setChecked(False)
            self.equal_aspect_box.setToolTip(
                "Lock the (x, y) aspect ratio. Useful for closed orbits "
                "in conservative systems; off by default since chaotic "
                "flows often span very different ranges on each axis."
            )
            controls.addRow(QLabel(""), self.equal_aspect_box)

            outer.addLayout(controls)

            action_row = QHBoxLayout()
            self.plot_button = QPushButton("Plot", self)
            self.plot_button.setObjectName("phase_plot_button")
            self.plot_button.setProperty("variant", "primary")
            self.plot_button.clicked.connect(self._refresh)
            action_row.addWidget(self.plot_button)

            self.status_label = QLabel("", self)
            self.status_label.setObjectName("phase_status")
            self.status_label.setWordWrap(True)
            action_row.addWidget(self.status_label, 1)
            outer.addLayout(action_row)

            # --- Canvas --------------------------------------------------
            fig = plot_phase_portrait(
                trajectory,
                ix=0,
                iy=1 if self._state_dim > 1 else 0,
                axes_labels=axes_labels,
                title=f"{self._system_name} phase portrait",
                facecolor=facecolor,
            )
            self.canvas = FigureCanvasQTAgg(fig)
            self.canvas.setObjectName("phase_canvas")
            outer.addWidget(self.canvas, 1)

            # Re-plot whenever the user picks a new axis or toggles aspect.
            self.x_axis_box.currentIndexChanged.connect(self._refresh)
            self.y_axis_box.currentIndexChanged.connect(self._refresh)
            self.equal_aspect_box.stateChanged.connect(self._refresh)

        # ----- public API ----------------------------------------------

        @property
        def state_dim(self) -> int:
            """The state dimension of the held trajectory."""
            return self._state_dim

        def set_trajectory(
            self,
            trajectory: Any,
            *,
            axes_labels: tuple[str, ...] | None = None,
            system_name: str | None = None,
        ) -> None:
            """Replace the snapshot the panel is showing and re-plot.

            Used by the dialog when the user clicks "Refresh from
            simulation" — but is also fine to call directly from
            scripts that want to drive the panel.
            """
            new_dim = _trajectory_state_dim(trajectory)
            if new_dim != self._state_dim:
                # Rebuild combos if the dimensionality changed (e.g. user
                # switched from Lorenz to DoublePendulum mid-session).
                self._state_dim = new_dim
                self._rebuild_axis_combos(axes_labels)
            self._trajectory = trajectory
            if axes_labels is not None:
                self._axes_labels = axes_labels
            if system_name is not None:
                self._system_name = system_name
            self._refresh()

        # ----- internal ------------------------------------------------

        def _rebuild_axis_combos(
            self, axes_labels: tuple[str, ...] | None
        ) -> None:
            for combo in (self.x_axis_box, self.y_axis_box):
                combo.blockSignals(True)
                combo.clear()
                for i in range(self._state_dim):
                    label = (
                        axes_labels[i]
                        if axes_labels is not None and i < len(axes_labels)
                        else f"y[{i}]"
                    )
                    combo.addItem(f"{i}: {label}", userData=i)
                combo.blockSignals(False)
            self.x_axis_box.setCurrentIndex(0)
            self.y_axis_box.setCurrentIndex(
                1 if self._state_dim > 1 else 0
            )

        def _refresh(self) -> None:
            ix = int(self.x_axis_box.currentData())
            iy = int(self.y_axis_box.currentData())
            if ix == iy:
                self.status_label.setText(
                    "X axis and Y axis must differ — pick a different "
                    "state component."
                )
                return
            try:
                fig = plot_phase_portrait(
                    self._trajectory,
                    ix=ix,
                    iy=iy,
                    axes_labels=self._axes_labels,
                    title=f"{self._system_name} phase portrait",
                    facecolor=self._facecolor,
                    equal_aspect=self.equal_aspect_box.isChecked(),
                )
            except (TypeError, ValueError) as exc:
                self.status_label.setText(f"{type(exc).__name__}: {exc}")
                return
            self.status_label.setText(f"y[{ix}] vs y[{iy}].")
            self._swap_canvas(fig)

        def _swap_canvas(self, fig: Any) -> None:
            new_canvas = FigureCanvasQTAgg(fig)
            new_canvas.setObjectName("phase_canvas")
            old = self.canvas
            self.layout().replaceWidget(old, new_canvas)
            old.setParent(None)
            old.deleteLater()
            self.canvas = new_canvas

    return PhasePanel


def build_phase_panel(
    trajectory: Any,
    *,
    axes_labels: tuple[str, ...] | None = None,
    system_name: str | None = None,
    facecolor: str | None = None,
    parent: QWidget | None = None,
) -> QWidget:
    """Convenience constructor for :class:`PhasePanel`.

    Wraps the lazy-built class so callers don't have to know about
    ``_build_panel_class``.
    """
    return _build_panel_class()(
        trajectory,
        axes_labels=axes_labels,
        system_name=system_name,
        facecolor=facecolor,
        parent=parent,
    )


def build_phase_dialog(
    trajectory: Any,
    *,
    axes_labels: tuple[str, ...] | None = None,
    system_name: str | None = None,
    facecolor: str | None = None,
    parent: QWidget | None = None,
) -> QWidget:
    """Build a ``QDockWidget`` wrapping :class:`PhasePanel` (FU-018).

    Pre-FU-018 the builder returned a free-floating ``QMainWindow``;
    post-FU-018 it returns a ``QDockWidget`` so the user can dock the
    Phase explorer beside the 3D viewport (or leave it floating, the
    default). napari's ``add_dock_widget`` pattern (PR #5483).

    The dock keeps ``WA_DeleteOnClose`` so closing tears down the C++
    object via the normal Qt lifecycle. The objectName
    (``"phase_dialog"``) and the ``.phase_panel`` attribute survive
    the migration so existing tests + scripted callers keep working.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDockWidget

    dock = QDockWidget(parent)
    dock.setObjectName("phase_dialog")
    title = system_name or str(
        getattr(trajectory, "system", "") or "trajectory"
    )
    dock.setWindowTitle(f"Phase portrait — {title}")
    dock.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dock.setAllowedAreas(
        Qt.DockWidgetArea.LeftDockWidgetArea
        | Qt.DockWidgetArea.RightDockWidgetArea
        | Qt.DockWidgetArea.BottomDockWidgetArea
        | Qt.DockWidgetArea.TopDockWidgetArea
    )
    dock.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable
        | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        | QDockWidget.DockWidgetFeature.DockWidgetClosable
    )

    panel = build_phase_panel(
        trajectory,
        axes_labels=axes_labels,
        system_name=system_name,
        facecolor=facecolor,
        parent=dock,
    )
    dock.setWidget(panel)
    dock.resize(720, 720)  # initial size when floating
    # Expose the embedded panel for tests and scripted callers.
    dock.phase_panel = panel  # type: ignore[attr-defined]
    return dock


def __getattr__(name: str) -> type:
    if name == "PhasePanel":
        return _build_panel_class()
    raise AttributeError(name)
