"""PySide6 panel for the Poincaré-section explorer (CSC-029 / W1).

Embeds a :class:`matplotlib.backends.backend_qtagg.FigureCanvasQTAgg`
inside a Qt widget so the user can:

1. Pick the *section axis* (which state-vector component the hyperplane
   normal aligns with — axis-aligned only, per the synthesis "defer
   arbitrary-normal until users ask").
2. Set the *offset* (constant ``c`` in the hyperplane equation
   :math:`n \\cdot y = c`).
3. Choose the *direction* of crossings to keep (upward / downward / both).
4. Set the integration window ``t_end`` and the transient
   ``t_transient`` discarded from crossing collection.
5. Pick the two state-vector components to project the crossings onto
   for the scatter (typically the two non-section components).
6. Press Compute and watch a status pill while a worker thread runs
   :func:`~chaotic_systems.core.poincare.poincare_section`.

The compute path was implemented since day one in
``src/chaotic_systems/core/poincare.py``; this panel is the wire-up
the internal-adversary brief CSC-029 flagged as the next "D1"-class
gap. The compute itself is bounded by ``solve_ivp`` event detection
on ``DOP853`` — typically a few seconds for ``t_end = 200`` on
Hénon-Heiles. There is no native progress callback in the underlying
function (events are collected internally by scipy), so the panel
shows a "Computing..." status string rather than a percentage bar.

Worker thread
-------------
:class:`_PoincareWorker` runs
:func:`~chaotic_systems.core.poincare.poincare_section` on a
:class:`PySide6.QtCore.QThread` and emits ``finished(Trajectory)`` on
completion or ``error(kind, message)`` on failure. Cancellation is
expressed by ``cancel()`` setting an internal flag the worker checks
after ``solve_ivp`` returns — there is no in-loop interrupt because
the underlying scipy call is opaque; for that reason cancellation
takes effect at the *next* completed compute, not mid-integration.

References
----------
- M. Hénon, C. Heiles, *The applicability of the third integral of
  motion: some numerical experiments*, Astron. J. 69 (1964), 73-79
  — the canonical Poincaré-section demo this panel reproduces.
- S. H. Strogatz, *Nonlinear Dynamics and Chaos* (2nd ed., 2015),
  §12.5 — Poincaré-section construction; the Hénon-Heiles section
  example is in §6.7.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from chaotic_systems.core.base import Trajectory
from chaotic_systems.core.poincare import poincare_section
from chaotic_systems.visualization.poincare_plot import plot_poincare_section

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from PySide6.QtWidgets import QWidget

__all__ = [
    "PoincarePanel",  # noqa: F822 - exported lazily via __getattr__ (PySide6 class)
    "build_poincare_dialog",
    "build_poincare_panel",
]

# Defaults are calibrated against the Hénon-Heiles canonical Poincaré
# section (Hénon & Heiles 1964 Fig. 4): x = 0 hyperplane, upward
# crossings (p_x > 0), 200 time units integration with the first 10
# discarded as transient. These produce ~50-150 section points
# depending on the IC's residence ratio inside the chaotic sea.
_DEFAULT_T_END: float = 200.0
_DEFAULT_T_TRANSIENT: float = 10.0
_DEFAULT_OFFSET: float = 0.0
# Tightening max_step keeps event-detection samples dense enough to
# catch every section crossing on the long Hénon-Heiles orbit. 0.5 is
# small enough for the section to land within a few solver steps; the
# default DOP853 RTOL handles the per-step accuracy.
_DEFAULT_MAX_STEP: float = 0.5
# Section-direction picker entries — order matches scipy.integrate
# event.direction semantics (+1 = upward, -1 = downward, 0 = both).
_DIRECTION_CHOICES: tuple[tuple[str, int], ...] = (
    ("Upward (n.dot(rhs) > 0)", +1),
    ("Downward (n.dot(rhs) < 0)", -1),
    ("Both", 0),
)


def _build_worker_class() -> type:
    """Build the worker class lazily so PySide6 is only imported on demand."""

    from PySide6.QtCore import QObject, Signal

    class _PoincareWorker(QObject):
        """Run :func:`poincare_section` on a worker thread.

        Emits ``finished(Trajectory)`` on success or
        ``error(kind, message)`` on failure. Cancellation is
        cooperative — the worker checks an internal flag *after*
        ``solve_ivp`` returns, so an in-flight compute is not
        interrupted, only the next one.
        """

        finished = Signal(object)  # Trajectory (or None on cancel)
        error = Signal(str, str)  # (kind, message)

        def __init__(
            self,
            system: Any,
            normal: np.ndarray,
            offset: float,
            direction: int,
            t_end: float,
            t_transient: float,
            max_step: float,
        ) -> None:
            super().__init__()
            self._system = system
            self._normal = np.asarray(normal, dtype=np.float64)
            self._offset = float(offset)
            self._direction = int(direction)
            self._t_end = float(t_end)
            self._t_transient = float(t_transient)
            self._max_step = float(max_step)
            self._cancelled = False

        def cancel(self) -> None:
            """Mark the compute as cancelled.

            Takes effect after the current ``solve_ivp`` returns; the
            ``finished`` signal carries ``None`` instead of the
            :class:`Trajectory` so consumers can distinguish cancel
            from genuine empty-result.
            """
            self._cancelled = True

        def run(self) -> None:
            try:
                crossings = poincare_section(
                    self._system,
                    normal=self._normal,
                    offset=self._offset,
                    direction=self._direction,
                    t_span=(0.0, self._t_end),
                    t_transient=self._t_transient,
                    max_step=self._max_step,
                )
            except (ValueError, KeyError, TypeError) as exc:
                self.error.emit(type(exc).__name__, str(exc))
                return
            except Exception as exc:  # pragma: no cover - last-resort guard
                self.error.emit("Exception", f"{type(exc).__name__}: {exc}")
                return
            if self._cancelled:
                self.finished.emit(None)
                return
            self.finished.emit(crossings)

    return _PoincareWorker


def _default_display_axes(state_dim: int, section_axis: int) -> tuple[int, int]:
    """Pick a sensible (ix, iy) pair excluding the section axis.

    For Hénon-Heiles with state ``[x, y, p_x, p_y]`` and section_axis=0
    (the x=0 hyperplane), this returns ``(1, 3) = (y, p_y)`` — the
    canonical Hénon-Heiles 1964 Fig. 4 projection. For state_dim < 3
    the fallback is the first non-section index plus the section
    axis itself; the panel's combo guard will error on identical
    indices.
    """
    others = [i for i in range(state_dim) if i != section_axis]
    if len(others) >= 2:
        # For 4D state, prefer (q-component, p-component) pairing — the
        # second free axis is typically the canonical conjugate. Pick
        # the first and the last of ``others``.
        return (others[0], others[-1])
    if len(others) == 1:
        return (others[0], section_axis)
    # state_dim == 1 — no meaningful 2D projection; pick a sentinel.
    return (0, 0)


def _build_panel_class() -> type:
    """Build the PoincarePanel class lazily; mirrors the other panel modules."""

    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from PySide6.QtCore import Qt, QThread
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    worker_cls = _build_worker_class()

    class PoincarePanel(QWidget):
        """Self-contained Poincaré-section explorer for one system.

        Construct against a
        :class:`~chaotic_systems.core.base.DynamicalSystem` instance.
        The widget owns the matplotlib figure and canvas; opening it
        in a top-level dialog is enough to give the user a fully
        functional explorer.

        The default UX is the canonical Hénon-Heiles demo: section
        through ``x = 0`` with upward crossings (``p_x > 0``),
        integrated for 200 time units after a 10 t.u. transient,
        projected onto ``(y, p_y)``.
        """

        def __init__(
            self,
            system: Any,
            *,
            axes_labels: tuple[str, ...] | None = None,
            facecolor: str | None = None,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self._system = system
            self._axes_labels = axes_labels
            self._facecolor = facecolor
            self._worker: object | None = None
            self._thread: QThread | None = None
            self._last_crossings: Trajectory | None = None
            self._state_dim = int(getattr(system, "state_dim", 0) or 0)
            if self._state_dim < 2:
                raise ValueError(
                    "PoincarePanel requires a system with state_dim >= 2; "
                    f"got state_dim={self._state_dim}"
                )

            from chaotic_systems.gui._panel_helpers import apply_panel_margins

            outer = QVBoxLayout(self)
            apply_panel_margins(outer)

            # --- Controls -------------------------------------------------
            controls = QFormLayout()
            controls.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

            # Section axis: which state-vector component the hyperplane
            # normal aligns with. Axis-aligned only by design.
            self.section_axis_box = QComboBox(self)
            self.section_axis_box.setObjectName("poincare_section_axis")
            for i in range(self._state_dim):
                self.section_axis_box.addItem(
                    f"{i}: {self._axis_label(i)}", userData=i
                )
            self.section_axis_box.setToolTip(
                "Which state component is the hyperplane normal aligned "
                "with? n = e_i for the chosen i."
            )
            controls.addRow(QLabel("Section axis"), self.section_axis_box)

            # Offset spinbox.
            self.offset_spin = QDoubleSpinBox(self)
            self.offset_spin.setObjectName("poincare_offset")
            self.offset_spin.setRange(-1.0e6, 1.0e6)
            self.offset_spin.setDecimals(4)
            self.offset_spin.setSingleStep(0.1)
            self.offset_spin.setValue(_DEFAULT_OFFSET)
            self.offset_spin.setToolTip(
                "Offset c in the hyperplane equation n . y = c. "
                "Default 0 = the section through the origin."
            )
            controls.addRow(QLabel("Offset (c)"), self.offset_spin)

            # Direction picker.
            self.direction_box = QComboBox(self)
            self.direction_box.setObjectName("poincare_direction")
            for label, value in _DIRECTION_CHOICES:
                self.direction_box.addItem(label, userData=value)
            self.direction_box.setToolTip(
                "Which crossings to keep: upward (n.dot(rhs) > 0), "
                "downward (n.dot(rhs) < 0), or both."
            )
            controls.addRow(QLabel("Direction"), self.direction_box)

            # Time window.
            self.t_end_spin = QDoubleSpinBox(self)
            self.t_end_spin.setObjectName("poincare_t_end")
            self.t_end_spin.setRange(1.0, 100_000.0)
            self.t_end_spin.setDecimals(1)
            self.t_end_spin.setSingleStep(10.0)
            self.t_end_spin.setValue(_DEFAULT_T_END)
            self.t_end_spin.setToolTip(
                "Total integration time. Longer windows collect more "
                "section points but cost proportionally more compute."
            )
            controls.addRow(QLabel("t_end"), self.t_end_spin)

            self.t_transient_spin = QDoubleSpinBox(self)
            self.t_transient_spin.setObjectName("poincare_t_transient")
            self.t_transient_spin.setRange(0.0, 10_000.0)
            self.t_transient_spin.setDecimals(1)
            self.t_transient_spin.setSingleStep(5.0)
            self.t_transient_spin.setValue(_DEFAULT_T_TRANSIENT)
            self.t_transient_spin.setToolTip(
                "Crossings before this time are discarded as transient. "
                "Set to ~5%-10% of t_end for stable section topology."
            )
            controls.addRow(QLabel("t_transient"), self.t_transient_spin)

            # Display-axis pickers (defaults excluding the section axis).
            ix0, iy0 = _default_display_axes(self._state_dim, 0)

            def _build_display_combo(name: str, default: int) -> QComboBox:
                combo = QComboBox(self)
                combo.setObjectName(name)
                for i in range(self._state_dim):
                    combo.addItem(f"{i}: {self._axis_label(i)}", userData=i)
                combo.setCurrentIndex(default)
                return combo

            self.display_x_box = _build_display_combo(
                "poincare_display_x", ix0
            )
            self.display_y_box = _build_display_combo(
                "poincare_display_y", iy0
            )
            controls.addRow(QLabel("Display X"), self.display_x_box)
            controls.addRow(QLabel("Display Y"), self.display_y_box)

            self.equal_aspect_box = QCheckBox("Equal aspect", self)
            self.equal_aspect_box.setObjectName("poincare_equal_aspect")
            self.equal_aspect_box.setChecked(False)
            self.equal_aspect_box.setToolTip(
                "Lock aspect ratio of the display axes. Recommended for "
                "Hamiltonian sections like Hénon-Heiles (y, p_y) where "
                "the two axes share units."
            )
            controls.addRow(QLabel(""), self.equal_aspect_box)

            outer.addLayout(controls)

            # Re-pick sensible display defaults when the user changes
            # the section axis. The user can override afterwards.
            self.section_axis_box.currentIndexChanged.connect(
                self._on_section_axis_changed
            )

            # --- Action row -----------------------------------------------
            action_row = QHBoxLayout()
            self.compute_button = QPushButton("Compute section", self)
            self.compute_button.setObjectName("poincare_compute")
            self.compute_button.setProperty("variant", "primary")
            self.compute_button.clicked.connect(self._on_compute)
            action_row.addWidget(self.compute_button)

            self.cancel_button = QPushButton("Cancel", self)
            self.cancel_button.setObjectName("poincare_cancel")
            self.cancel_button.setEnabled(False)
            self.cancel_button.clicked.connect(self._on_cancel)
            action_row.addWidget(self.cancel_button)

            self.status_label = QLabel(
                "Press Compute to map the Poincaré section.", self
            )
            self.status_label.setObjectName("poincare_status")
            self.status_label.setWordWrap(True)
            action_row.addWidget(self.status_label, 1)
            outer.addLayout(action_row)

            # --- Canvas (placeholder until first compute) -----------------
            placeholder = self._placeholder_crossings()
            fig = plot_poincare_section(
                placeholder,
                ix=ix0,
                iy=iy0,
                axes_labels=axes_labels,
                title=f"{self._system_name()} Poincaré section (pending)",
                facecolor=facecolor,
            )
            self.canvas = FigureCanvasQTAgg(fig)
            self.canvas.setObjectName("poincare_canvas")
            outer.addWidget(self.canvas, 1)

            # Re-plot the canvas without re-computing when the user only
            # changes the display axes / aspect.
            self.display_x_box.currentIndexChanged.connect(self._refresh_plot)
            self.display_y_box.currentIndexChanged.connect(self._refresh_plot)
            self.equal_aspect_box.stateChanged.connect(self._refresh_plot)

        # ----- public API ----------------------------------------------

        @property
        def state_dim(self) -> int:
            """The state dimension of the held system."""
            return self._state_dim

        def last_crossings(self) -> Trajectory | None:
            """Return the most-recently-computed section result (or ``None``)."""
            return self._last_crossings

        # ----- helpers ------------------------------------------------

        def _system_name(self) -> str:
            return str(getattr(self._system, "name", "") or "system")

        def _axis_label(self, idx: int) -> str:
            if (
                self._axes_labels is not None
                and 0 <= idx < len(self._axes_labels)
            ):
                return str(self._axes_labels[idx])
            return f"y[{idx}]"

        def _placeholder_crossings(self) -> Trajectory:
            """Empty :class:`Trajectory` so the canvas has something to draw."""
            return Trajectory(
                t=np.array([], dtype=np.float64),
                y=np.zeros((0, self._state_dim), dtype=np.float64),
                system=self._system_name(),
                params={},
                integrator="poincare",
            )

        def _on_section_axis_changed(self) -> None:
            section_axis = int(self.section_axis_box.currentData())
            ix, iy = _default_display_axes(self._state_dim, section_axis)
            self.display_x_box.blockSignals(True)
            self.display_y_box.blockSignals(True)
            self.display_x_box.setCurrentIndex(ix)
            self.display_y_box.setCurrentIndex(iy)
            self.display_x_box.blockSignals(False)
            self.display_y_box.blockSignals(False)
            # Only re-render if we actually have data; placeholder render
            # is unchanged.
            if self._last_crossings is not None:
                self._refresh_plot()

        # ----- actions ------------------------------------------------

        def _on_compute(self) -> None:
            if self._thread is not None and self._thread.isRunning():
                return
            section_axis = int(self.section_axis_box.currentData())
            normal = np.zeros(self._state_dim, dtype=np.float64)
            normal[section_axis] = 1.0
            offset = float(self.offset_spin.value())
            direction = int(self.direction_box.currentData())
            t_end = float(self.t_end_spin.value())
            t_transient = float(self.t_transient_spin.value())
            if t_transient >= t_end:
                self.status_label.setText(
                    "t_transient must be < t_end — discarding everything "
                    "leaves no crossings."
                )
                return

            self.compute_button.setEnabled(False)
            self.cancel_button.setEnabled(True)
            self.status_label.setText(
                f"Computing {self._system_name()} section through "
                f"{self._axis_label(section_axis)} = {offset:g} "
                f"over t in [0, {t_end:g}]..."
            )

            worker = worker_cls(
                system=self._system,
                normal=normal,
                offset=offset,
                direction=direction,
                t_end=t_end,
                t_transient=t_transient,
                max_step=_DEFAULT_MAX_STEP,
            )
            thread = QThread(self)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
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

        def _on_finished(self, crossings: Trajectory | None) -> None:
            self.cancel_button.setEnabled(False)
            self.compute_button.setEnabled(True)
            if crossings is None:
                self.status_label.setText("Cancelled.")
                return
            self._last_crossings = crossings
            n_pts = int(crossings.y.shape[0])
            self.status_label.setText(
                f"Done: {n_pts} section crossings collected."
            )
            self._refresh_plot()

        def _on_error(self, kind: str, message: str) -> None:
            self.cancel_button.setEnabled(False)
            self.compute_button.setEnabled(True)
            self.status_label.setText(f"{kind}: {message}")

        def _cleanup_thread(self) -> None:
            if self._worker is not None:
                self._worker.deleteLater()  # type: ignore[attr-defined]
            if self._thread is not None:
                self._thread.deleteLater()
            self._worker = None
            self._thread = None

        def _refresh_plot(self) -> None:
            ix = int(self.display_x_box.currentData())
            iy = int(self.display_y_box.currentData())
            if ix == iy:
                self.status_label.setText(
                    "Display X and Y must differ — pick different "
                    "state components."
                )
                return
            crossings = (
                self._last_crossings
                if self._last_crossings is not None
                else self._placeholder_crossings()
            )
            title_suffix = (
                "Poincaré section"
                if self._last_crossings is not None
                else "Poincaré section (pending)"
            )
            try:
                fig = plot_poincare_section(
                    crossings,
                    ix=ix,
                    iy=iy,
                    axes_labels=self._axes_labels,
                    title=f"{self._system_name()} {title_suffix}",
                    facecolor=self._facecolor,
                    equal_aspect=self.equal_aspect_box.isChecked(),
                )
            except (TypeError, ValueError) as exc:
                self.status_label.setText(f"{type(exc).__name__}: {exc}")
                return
            self._swap_canvas(fig)

        def _swap_canvas(self, fig: Any) -> None:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

            from chaotic_systems.gui._panel_helpers import swap_mpl_canvas

            new_canvas = FigureCanvasQTAgg(fig)
            new_canvas.setObjectName("poincare_canvas")
            swap_mpl_canvas(self.layout(), self.canvas, new_canvas)
            self.canvas = new_canvas

    return PoincarePanel


def build_poincare_panel(
    system: Any,
    *,
    axes_labels: tuple[str, ...] | None = None,
    facecolor: str | None = None,
    parent: QWidget | None = None,
) -> QWidget:
    """Convenience constructor for :class:`PoincarePanel`.

    Wraps the lazy-built class so callers don't have to know about
    ``_build_panel_class``.
    """
    return _build_panel_class()(
        system,
        axes_labels=axes_labels,
        facecolor=facecolor,
        parent=parent,
    )


def build_poincare_dialog(
    system: Any,
    *,
    axes_labels: tuple[str, ...] | None = None,
    facecolor: str | None = None,
    parent: QWidget | None = None,
) -> QWidget:
    """Build a ``QDockWidget`` wrapping :class:`PoincarePanel` (FU-018).

    Pre-FU-018 the builder returned a free-floating ``QMainWindow``;
    post-FU-018 a ``QDockWidget`` so the user can dock the Poincaré
    explorer beside the 3D viewport. ``WA_DeleteOnClose`` cleans up
    on close via the normal Qt lifecycle.
    """
    from chaotic_systems.gui._panel_helpers import make_panel_dialog

    title = str(getattr(system, "name", "") or "system")
    panel = build_poincare_panel(
        system,
        axes_labels=axes_labels,
        facecolor=facecolor,
        parent=parent,
    )
    return make_panel_dialog(
        object_name="poincare_dialog",
        title=f"Poincaré section — {title}",
        panel=panel,
        size=(760, 800),
        parent=parent,
        panel_attr="poincare_panel",
    )


def __getattr__(name: str) -> type:
    if name == "PoincarePanel":
        return _build_panel_class()
    raise AttributeError(name)
