"""PySide6 panel for the recurrence-plot / RQA tool (D5).

Operates on a single trajectory snapshot (same pattern as
:mod:`chaotic_systems.gui.phase_panel`): the main window passes in
the most recent simulation result, the user picks the recurrence
threshold ``epsilon``, and the panel renders the recurrence matrix
with RQA scalars (RR, DET, LAM, L_max, V_max, ENTR) overlaid.

Long trajectories are *subsampled* to a hard cap of
:data:`_MAX_PLOT_N` before the matrix is computed — the recurrence
matrix is ``O(N²)`` in memory, so a 4000-sample trajectory at the
full resolution would allocate ~16 MB and take seconds to render. The
panel subsamples uniformly so the picture's geometric structure is
preserved (recurrent diagonals stay diagonal, just at lower
resolution).

References
----------
- N. Marwan, M. C. Romano, M. Thiel, J. Kurths, *Recurrence plots for
  the analysis of complex systems*, Phys. Rep. 438 (2007), 237-329 —
  Figs. 1-6 are the canonical reference for what the user is
  looking at.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from chaotic_systems.core.recurrence import (
    RQAStats,
    recurrence_matrix,
    rqa,
    suggest_epsilon,
)
from chaotic_systems.visualization.recurrence_plot import plot_recurrence

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from PySide6.QtWidgets import QWidget

__all__ = [
    "RecurrencePanel",  # noqa: F822 - exported lazily via __getattr__
    "build_recurrence_dialog",
    "build_recurrence_panel",
]

# Maximum recurrence-matrix side length the panel will compute. At
# N = 800 the matrix is ~640 KB and ``recurrence_matrix`` returns in
# well under a screen frame — the panel feels live. Longer
# trajectories are subsampled with ``np.linspace(0, len-1, _MAX_PLOT_N)``
# indices. Going above 1500 stops feeling interactive on a typical
# laptop and the bigger picture rarely adds information.
_MAX_PLOT_N: int = 800

# Default ``epsilon`` heuristic — fraction of bounding-box diagonal.
# 10% is the Marwan et al. 2007 §2.1 midpoint between "too sparse"
# (< 5%) and "saturated" (> 25%).
_DEFAULT_EPSILON_FRACTION: float = 0.10


def _trajectory_states(trajectory: Any) -> np.ndarray:
    """Pull a ``(N, d)`` ndarray out of any Trajectory-like input."""
    if not hasattr(trajectory, "y"):
        raise TypeError(
            "recurrence panel input must have a .y attribute; got "
            f"{type(trajectory).__name__}"
        )
    arr = np.ascontiguousarray(trajectory.y, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[0] < 2:
        raise ValueError(
            f"trajectory.y must be a (N>=2, d) array; got shape {arr.shape!r}"
        )
    return arr


def _subsample(states: np.ndarray, max_n: int = _MAX_PLOT_N) -> np.ndarray:
    """Return at most ``max_n`` rows of ``states``, uniformly spaced.

    Diagonals in the recurrence plot stay diagonal under uniform
    subsampling (just at lower resolution), so the geometric story
    survives.
    """
    n = int(states.shape[0])
    if n <= int(max_n):
        return states
    idx = np.linspace(0, n - 1, int(max_n)).round().astype(np.int64)
    return states[idx]


def _build_panel_class() -> type:
    """Build the RecurrencePanel class lazily; mirrors the other panels."""

    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QDoubleSpinBox,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QSpinBox,
        QVBoxLayout,
        QWidget,
    )

    class RecurrencePanel(QWidget):
        """Self-contained recurrence-plot / RQA explorer."""

        def __init__(
            self,
            trajectory: Any,
            *,
            system_name: str | None = None,
            dark: bool = True,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self._states = _subsample(_trajectory_states(trajectory))
            self._system_name = (
                system_name
                if system_name is not None
                else str(getattr(trajectory, "system", "") or "trajectory")
            )
            self._dark = bool(dark)
            self._last_stats: RQAStats | None = None
            self._last_matrix: np.ndarray | None = None

            from chaotic_systems.gui._panel_helpers import apply_panel_margins

            outer = QVBoxLayout(self)
            apply_panel_margins(outer)

            controls = QFormLayout()
            controls.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

            initial_eps = suggest_epsilon(
                self._states, fraction=_DEFAULT_EPSILON_FRACTION
            )

            self.epsilon_spin = QDoubleSpinBox(self)
            self.epsilon_spin.setObjectName("recurrence_epsilon")
            self.epsilon_spin.setRange(1e-9, 1e6)
            self.epsilon_spin.setDecimals(6)
            self.epsilon_spin.setValue(float(initial_eps))
            self.epsilon_spin.setSingleStep(float(initial_eps) * 0.1)
            self.epsilon_spin.setToolTip(
                "Recurrence threshold ε. Marwan et al. 2007 §2.1 "
                "suggests 5-25% of the trajectory's bounding-box "
                "diagonal; the default starts at 10%."
            )
            controls.addRow(QLabel("epsilon"), self.epsilon_spin)

            self.l_min_spin = QSpinBox(self)
            self.l_min_spin.setObjectName("recurrence_l_min")
            self.l_min_spin.setRange(1, 50)
            self.l_min_spin.setValue(2)
            self.l_min_spin.setToolTip(
                "Minimum diagonal length counted as a line "
                "(Marwan §3.3; canonical = 2)."
            )
            controls.addRow(QLabel("l_min"), self.l_min_spin)

            self.v_min_spin = QSpinBox(self)
            self.v_min_spin.setObjectName("recurrence_v_min")
            self.v_min_spin.setRange(1, 50)
            self.v_min_spin.setValue(2)
            self.v_min_spin.setToolTip(
                "Minimum vertical length counted as a line "
                "(Marwan §3.4; canonical = 2)."
            )
            controls.addRow(QLabel("v_min"), self.v_min_spin)

            outer.addLayout(controls)

            action_row = QHBoxLayout()
            self.compute_button = QPushButton("Compute", self)
            self.compute_button.setObjectName("recurrence_compute")
            self.compute_button.setProperty("variant", "primary")
            self.compute_button.clicked.connect(self._on_compute)
            action_row.addWidget(self.compute_button)

            self.status_label = QLabel("", self)
            self.status_label.setObjectName("recurrence_status")
            self.status_label.setWordWrap(True)
            action_row.addWidget(self.status_label, 1)
            outer.addLayout(action_row)

            # Initial render at the default epsilon so the canvas is
            # immediately populated (no "press Compute" dead state).
            initial_matrix = recurrence_matrix(self._states, epsilon=float(initial_eps))
            initial_stats = rqa(initial_matrix)
            fig = plot_recurrence(
                initial_matrix,
                stats=initial_stats,
                title=f"{self._system_name} recurrence plot",
                dark=self._dark,
            )
            self._last_matrix = initial_matrix
            self._last_stats = initial_stats
            self.canvas = FigureCanvasQTAgg(fig)
            self.canvas.setObjectName("recurrence_canvas")
            outer.addWidget(self.canvas, 1)
            self._refresh_status(initial_stats)

        # ----- public read-only accessors --------------------------------

        def last_stats(self) -> RQAStats | None:
            """Return the most-recently-computed RQA stats (or ``None``)."""
            return self._last_stats

        def last_matrix(self) -> np.ndarray | None:
            """Return the most-recently-computed recurrence matrix."""
            return self._last_matrix

        # ----- actions ---------------------------------------------------

        def _on_compute(self) -> None:
            epsilon = float(self.epsilon_spin.value())
            l_min = int(self.l_min_spin.value())
            v_min = int(self.v_min_spin.value())
            if epsilon <= 0.0:
                self.status_label.setText("epsilon must be positive.")
                return
            try:
                matrix = recurrence_matrix(self._states, epsilon=epsilon)
                stats = rqa(matrix, l_min=l_min, v_min=v_min)
            except (ValueError, TypeError) as exc:
                self.status_label.setText(f"{type(exc).__name__}: {exc}")
                return
            self._last_matrix = matrix
            self._last_stats = stats
            self._refresh_status(stats)
            self._swap_canvas(
                plot_recurrence(
                    matrix,
                    stats=stats,
                    title=f"{self._system_name} recurrence plot",
                    dark=self._dark,
                )
            )

        def _refresh_status(self, stats: RQAStats) -> None:
            self.status_label.setText(
                f"N={stats.n}  RR={stats.rr:.4f}  DET={stats.det:.4f}  "
                f"LAM={stats.lam:.4f}  L_max={stats.l_max}  "
                f"ENTR={stats.entr:.3f}"
            )

        def _swap_canvas(self, fig: Any) -> None:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

            from chaotic_systems.gui._panel_helpers import swap_mpl_canvas

            new_canvas = FigureCanvasQTAgg(fig)
            new_canvas.setObjectName("recurrence_canvas")
            swap_mpl_canvas(self.layout(), self.canvas, new_canvas)
            self.canvas = new_canvas

    return RecurrencePanel


def build_recurrence_panel(
    trajectory: Any,
    *,
    system_name: str | None = None,
    dark: bool = True,
    parent: QWidget | None = None,
) -> QWidget:
    """Convenience constructor for :class:`RecurrencePanel`."""
    return _build_panel_class()(
        trajectory, system_name=system_name, dark=dark, parent=parent
    )


def build_recurrence_dialog(
    trajectory: Any,
    *,
    system_name: str | None = None,
    dark: bool = True,
    parent: QWidget | None = None,
) -> QWidget:
    """Build a ``QDockWidget`` wrapping :class:`RecurrencePanel` (FU-018)."""
    from chaotic_systems.gui._panel_helpers import make_panel_dialog

    title = system_name or str(
        getattr(trajectory, "system", "") or "trajectory"
    )
    panel = build_recurrence_panel(
        trajectory, system_name=system_name, dark=dark, parent=parent
    )
    return make_panel_dialog(
        object_name="recurrence_dialog",
        title=f"Recurrence plot — {title}",
        panel=panel,
        size=(780, 820),
        parent=parent,
        panel_attr="recurrence_panel",
    )


def __getattr__(name: str) -> type:
    if name == "RecurrencePanel":
        return _build_panel_class()
    raise AttributeError(name)
