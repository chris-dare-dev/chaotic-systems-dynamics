"""chaotic_systems — simulation and visualization of chaotic dynamical systems.

See ``CONTEXT.md`` at the repository root for current state and design
decisions.

Subpackages:

- :mod:`chaotic_systems.core` — base abstractions (``DynamicalSystem``,
  ``Integrator``, Lyapunov / Poincaré diagnostics).
- :mod:`chaotic_systems.systems` — concrete chaotic systems (Lorenz, Rossler, ...).
- :mod:`chaotic_systems.integrators` — numerical integrators (adaptive,
  fixed-step, symplectic).
- :mod:`chaotic_systems.visualization` — 3D rendering, LaTeX rendering, video
  export.
- :mod:`chaotic_systems.gui` — native desktop window.
"""

from __future__ import annotations

try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    try:
        __version__ = _pkg_version("chaotic-systems-dynamics")
    except PackageNotFoundError:  # pragma: no cover - editable install fallback
        __version__ = "0.1.0"
except ImportError:  # pragma: no cover - Python <3.8 (we require 3.12)
    __version__ = "0.1.0"

__all__ = ["__version__"]
