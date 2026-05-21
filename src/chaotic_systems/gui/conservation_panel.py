"""PySide6 panel for the conservation overlay (V3).

Renders the energy drift :math:`\\Delta E(t) = E(y(t)) - E(y(0))` for
a single trajectory snapshot. The panel is the GUI surface of V3
from ``docs/proposals/capability-roadmap-2026-05-17.md`` —
specifically, it gives the user the in-app evidence the project
already-shipped symplectic-family integrators were supposed to
justify. Pick yoshida4 on Hénon-Heiles, run, open this panel, watch
the line stay glued to zero. Switch to RK45 and watch it slowly
drift. That's the pedagogical payoff Hairer-Lubich-Wanner (2006)
§I.1 is selling.

Like the V1 phase-portrait panel, this is read-only against a single
trajectory snapshot — no worker thread is needed because
``np.array([energy_fn(y) for y in trajectory.y])`` for a few-thousand-
point trajectory completes in well under a screen frame.

The companion :mod:`chaotic_systems.visualization.conservation_plot`
module is the pure-matplotlib renderer.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import numpy as np

from chaotic_systems.core.base import FloatArray
from chaotic_systems.visualization.conservation_plot import plot_conservation

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from PySide6.QtWidgets import QWidget

__all__ = [
    "ConservationPanel",  # noqa: F822 - exported lazily via __getattr__
    "build_conservation_dialog",
    "build_conservation_panel",
    "system_has_energy",
]

# Subsampling cap. Energy evaluation is per-sample Python; 1000-point
# trajectories render in <50 ms on every test system. Larger
# trajectories are downsampled uniformly to keep the panel snappy —
# energy drift is a low-frequency signal so subsampling doesn't lose
# information.
_MAX_PLOT_N: int = 1000


def system_has_energy(system: Any) -> bool:
    """Return ``True`` iff ``system`` exposes a callable ``.energy`` method.

    Used by the main window's toolbar-action gate so the "Conservation
    overlay…" entry is only enabled for systems where the diagnostic
    is meaningful (DoublePendulum, HenonHeiles, Duffing — the three
    that ship a ``.energy(y, params)`` accessor). Discrete maps and
    non-energy ODE systems (Lorenz, Rossler, Chua, etc.) return False.
    """
    fn = getattr(system, "energy", None)
    return callable(fn)


def _trajectory_arrays(trajectory: Any) -> tuple[FloatArray, FloatArray]:
    """Pull (t, y) from a Trajectory-like, raise informatively otherwise."""
    if not hasattr(trajectory, "t") or not hasattr(trajectory, "y"):
        raise TypeError(
            "conservation panel input must expose .t and .y; got "
            f"{type(trajectory).__name__}"
        )
    ts = np.ascontiguousarray(trajectory.t, dtype=np.float64)
    ys = np.ascontiguousarray(trajectory.y, dtype=np.float64)
    if ys.ndim != 2 or ys.shape[0] < 2:
        raise ValueError(
            f"trajectory.y must be a (N>=2, d) array; got shape {ys.shape!r}"
        )
    if ts.shape[0] != ys.shape[0]:
        raise ValueError(
            f"trajectory.t length {ts.shape[0]} != y rows {ys.shape[0]}"
        )
    return ts, ys


def _subsample(
    ts: FloatArray, ys: FloatArray, max_n: int = _MAX_PLOT_N
) -> tuple[FloatArray, FloatArray]:
    """Return at most ``max_n`` rows of (ts, ys), uniformly spaced."""
    n = int(ts.shape[0])
    if n <= int(max_n):
        return ts, ys
    idx = np.linspace(0, n - 1, int(max_n)).round().astype(np.int64)
    return ts[idx], ys[idx]


class _SubsampledTrajectory:
    """Lightweight Trajectory shim — only ``.t`` / ``.y`` / ``.system``.

    Built once at panel-construction time so the plot helper doesn't
    re-subsample on every render and so the un-touched original
    trajectory remains accessible elsewhere via main-window state.
    """

    __slots__ = ("t", "y", "system")

    def __init__(self, t: FloatArray, y: FloatArray, system: str) -> None:
        self.t = t
        self.y = y
        self.system = system


def _build_panel_class() -> type:
    """Build the ConservationPanel class lazily so PySide6 is only
    imported on demand. Mirrors the other panel modules."""

    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from PySide6.QtWidgets import (
        QHBoxLayout,
        QLabel,
        QVBoxLayout,
        QWidget,
    )

    class ConservationPanel(QWidget):
        """Self-contained conservation-overlay panel.

        Constructor signature is
        ``ConservationPanel(trajectory, energy_fn, *, system_name=None,
        facecolor=None, parent=None)``. The ``energy_fn`` should be
        the bound ``system.energy`` (with parameters already folded
        in via ``functools.partial`` if non-default). The panel
        subsamples ``trajectory`` to ``_MAX_PLOT_N`` rows uniformly
        before plotting.
        """

        def __init__(
            self,
            trajectory: Any,
            energy_fn: Callable[[FloatArray], float],
            *,
            system_name: str | None = None,
            facecolor: str | None = None,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            ts, ys = _trajectory_arrays(trajectory)
            ts, ys = _subsample(ts, ys)
            self._system_name = (
                system_name
                if system_name is not None
                else str(getattr(trajectory, "system", "") or "trajectory")
            )
            self._traj = _SubsampledTrajectory(ts, ys, self._system_name)
            self._energy_fn = energy_fn
            self._facecolor = facecolor

            outer = QVBoxLayout(self)
            outer.setContentsMargins(8, 8, 8, 8)
            outer.setSpacing(6)

            # Header strip with the system name + a static caption that
            # tells the user what the line means without forcing them to
            # decode the axis label.
            header = QHBoxLayout()
            self.title_label = QLabel(
                f"<b>{self._system_name}</b> — energy drift "
                "ΔE(t) = E(t) − E(0)",
                self,
            )
            self.title_label.setObjectName("conservation_title")
            header.addWidget(self.title_label)
            header.addStretch(1)
            outer.addLayout(header)

            # The plot — drawn once at construction time.
            fig = plot_conservation(
                self._traj,
                self._energy_fn,
                title=f"{self._system_name} energy drift",
                facecolor=facecolor,
            )
            self.canvas = FigureCanvasQTAgg(fig)
            self.canvas.setObjectName("conservation_canvas")
            outer.addWidget(self.canvas, 1)

            # Bottom status caption — surfaces the numerical headline so
            # the user can read the integrator's conservation quality
            # without reading the in-plot annotation. ``_last_max_drift``
            # is stashed for test introspection; the energy eval is
            # repeated rather than threaded through from ``plot_conservation``
            # to keep the panel's interface to the plot helper narrow.
            self._last_max_drift: float = 0.0
            try:
                energies = np.array(
                    [float(self._energy_fn(y)) for y in self._traj.y],
                    dtype=np.float64,
                )
                e0 = float(energies[0])
                max_drift = float(np.max(np.abs(energies - e0)))
                denom = abs(e0) if abs(e0) > 1e-12 else 1.0
                rel = max_drift / denom
                self._last_max_drift = max_drift
                self.status_label = QLabel(
                    f"E(0) = {e0:+.4g}    "
                    f"|ΔE|_max = {max_drift:.3e}    "
                    f"|ΔE|/|E₀| = {rel:.3e}",
                    self,
                )
            except (TypeError, ValueError, KeyError) as exc:
                self.status_label = QLabel(f"Energy eval failed: {exc}", self)
            self.status_label.setObjectName("conservation_status")
            self.status_label.setWordWrap(True)
            outer.addWidget(self.status_label)

        # ----- public read-only accessors used by tests -----------------

        def max_drift(self) -> float:
            """Return ``|ΔE|_max`` for the displayed trajectory."""
            return float(self._last_max_drift)

    return ConservationPanel


def build_conservation_panel(
    trajectory: Any,
    energy_fn: Callable[[FloatArray], float],
    *,
    system_name: str | None = None,
    facecolor: str | None = None,
    parent: QWidget | None = None,
) -> QWidget:
    """Convenience constructor for :class:`ConservationPanel`."""
    return _build_panel_class()(
        trajectory,
        energy_fn,
        system_name=system_name,
        facecolor=facecolor,
        parent=parent,
    )


def build_conservation_dialog(
    trajectory: Any,
    energy_fn: Callable[[FloatArray], float],
    *,
    system_name: str | None = None,
    facecolor: str | None = None,
    parent: QWidget | None = None,
) -> QWidget:
    """Build a top-level window wrapping :class:`ConservationPanel`."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

    win = QMainWindow(parent)
    win.setObjectName("conservation_dialog")
    title = system_name or str(
        getattr(trajectory, "system", "") or "trajectory"
    )
    win.setWindowTitle(f"Conservation overlay — {title}")
    win.resize(720, 460)
    win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

    central = QWidget(win)
    outer = QVBoxLayout(central)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    panel = build_conservation_panel(
        trajectory,
        energy_fn,
        system_name=system_name,
        facecolor=facecolor,
        parent=central,
    )
    outer.addWidget(panel, 1)
    win.setCentralWidget(central)
    win.conservation_panel = panel  # type: ignore[attr-defined]
    return win


def __getattr__(name: str) -> type:
    if name == "ConservationPanel":
        return _build_panel_class()
    raise AttributeError(name)
