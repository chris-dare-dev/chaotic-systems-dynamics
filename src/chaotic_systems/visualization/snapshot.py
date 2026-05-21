"""Viewport PNG snapshot helper (V4).

Wraps :meth:`pyvista.Plotter.screenshot` with a uniform ``(renderer
or plotter, path)`` API so the GUI can call it identically to the
other export paths in :mod:`chaotic_systems.io`. PyVista is a runtime
dependency of the project, so the import here is unconditional —
the snapshot path is meaningful only when a renderer / plotter is
attached.

The output PNG resolution is whatever the underlying plotter window
is currently sized at; callers can pass an explicit ``size=(w, h)``
to override (PyVista honors this even for embedded ``QtInteractor``
plotters by temporarily resizing the off-screen buffer).

References
----------
- PyVista 0.44+ ``Plotter.screenshot`` documentation:
  https://docs.pyvista.org/api/plotting/_autosummary/pyvista.plotter.screenshot
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def save_viewport_png(
    renderer_or_plotter: Any,
    path: str | Path,
    *,
    size: tuple[int, int] | None = None,
    transparent_background: bool = False,
) -> Path:
    """Save the current viewport to a PNG file.

    Parameters
    ----------
    renderer_or_plotter
        Either a :class:`~chaotic_systems.visualization.Renderer3D`
        (we extract its ``_plotter`` attribute) or a bare
        :class:`pyvista.Plotter` (or :class:`pyvistaqt.QtInteractor`)
        instance.
    path
        Destination PNG path. ``.png`` extension is conventional but
        not required.
    size
        Optional ``(width, height)`` in pixels. ``None`` uses the
        plotter's current window size.
    transparent_background
        If ``True``, the PNG's background pixels are written with
        alpha = 0 (useful for figure embedding); default ``False``
        keeps the plotter's background color.

    Returns
    -------
    Path
        Absolute path to the written PNG.

    Raises
    ------
    RuntimeError
        If ``renderer_or_plotter`` has no attached plotter (e.g. a
        bare :class:`Renderer3D` that was never ``.attach()``\\ed or
        ``.show()``\\ed).
    """
    plotter = _resolve_plotter(renderer_or_plotter)
    if plotter is None:
        raise RuntimeError(
            "save_viewport_png: no attached plotter — call "
            "Renderer3D.attach(qt_interactor) or .show() first."
        )
    dest = Path(path).expanduser().resolve()
    # PyVista's signature is ``screenshot(filename=None, ...)``; passing
    # the path makes it write the file and return the rendered ndarray.
    # ``window_size`` is the standard kwarg for forcing dimensions.
    kwargs: dict[str, Any] = {
        "filename": str(dest),
        "transparent_background": bool(transparent_background),
    }
    if size is not None:
        kwargs["window_size"] = (int(size[0]), int(size[1]))
    plotter.screenshot(**kwargs)
    return dest


def _resolve_plotter(obj: Any) -> Any | None:
    """Extract the underlying ``pyvista.Plotter`` from a Renderer3D or pass through.

    The Renderer3D class holds its plotter in the ``_plotter`` attribute
    (set by ``.attach()`` or ``.show()``). We accept either it or a
    bare plotter so callers don't have to remember which one they have.
    """
    if obj is None:
        return None
    # A bare plotter quacks like a screenshot()-haver.
    if hasattr(obj, "screenshot") and not hasattr(obj, "_plotter"):
        return obj
    inner = getattr(obj, "_plotter", None)
    if inner is not None and hasattr(inner, "screenshot"):
        return inner
    # Last resort: try the duck-typed path even on something that
    # claims to be a Renderer3D but has no _plotter populated yet.
    if hasattr(obj, "screenshot"):
        return obj
    return None


__all__ = ["save_viewport_png"]
