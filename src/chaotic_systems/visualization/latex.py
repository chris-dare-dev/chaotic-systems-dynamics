"""LaTeX rendering utilities.

We use matplotlib's mathtext renderer to turn a LaTeX string (or a SymPy
expression) into a raster image. This keeps the dependency footprint small
and avoids requiring a TeX installation. Mathtext supports a useful subset
of LaTeX; for full LaTeX, an optional path via ``matplotlib`` + ``usetex``
is available if the user has a TeX install, but we do not require it.

The output is either a ``numpy.ndarray`` (``H x W x 4`` RGBA, uint8) or, if
PySide6 is available, a ``QImage`` ready to be drawn in the GUI panel.

Public API
----------
- :func:`latex_to_array` — render LaTeX to an RGBA ndarray.
- :func:`latex_to_qimage` — render LaTeX to a ``QImage`` (raises ``RuntimeError``
  if PySide6 is unavailable in the current environment).
- :func:`sympy_to_latex` — wrap :func:`sympy.latex` with sane defaults.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from PySide6.QtGui import QImage

__all__ = [
    "latex_to_array",
    "latex_to_qimage",
    "sympy_to_latex",
]


_ALIGN_ENVS = (
    "aligned",
    "align",
    "align*",
    "cases",
    "matrix",
    "pmatrix",
    "bmatrix",
)


def _strip_alignment_env(latex: str) -> list[str]:
    """Strip an ``aligned``/``align``-style environment to a list of lines.

    matplotlib mathtext does not support these environments. We render each
    row as a standalone equation and stack them vertically. Alignment
    characters (``&``) are dropped.

    Returns the list of mathtext-ready row strings. If no environment is
    detected, returns ``[latex]``.
    """

    import re

    body: str | None = None
    for env in _ALIGN_ENVS:
        # Match \begin{env}...\end{env} non-greedily.
        m = re.search(
            rf"\\begin\{{{re.escape(env)}\}}(.*?)\\end\{{{re.escape(env)}\}}",
            latex,
            flags=re.DOTALL,
        )
        if m is not None:
            body = m.group(1)
            break
    if body is None:
        return [latex]
    # Split on \\ row separators (matplotlib's row break), drop empty trailing rows.
    rows = [row.strip() for row in body.split(r"\\")]
    rows = [r.replace("&", "") for r in rows if r]
    return rows


def _render_with_matplotlib(
    latex: str,
    *,
    fontsize: int,
    dpi: int,
    color: str,
    background: str | None,
) -> np.ndarray:
    """Internal: render via matplotlib's mathtext to an RGBA buffer."""

    import matplotlib

    # Use a non-interactive backend so this works headless.
    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt

    if background is None:
        face = (0.0, 0.0, 0.0, 0.0)
    else:
        face = background  # type: ignore[assignment]

    fig = plt.figure(figsize=(0.01, 0.01), dpi=dpi)
    try:
        fig.patch.set_alpha(0.0 if background is None else 1.0)
        if background is not None:
            fig.patch.set_facecolor(background)
        text = fig.text(
            0.0,
            0.0,
            f"${latex}$",
            fontsize=fontsize,
            color=color,
            verticalalignment="bottom",
            horizontalalignment="left",
        )

        # Measure the rendered text and resize the figure to fit it tightly.
        fig.canvas.draw()
        bbox = text.get_window_extent(renderer=fig.canvas.get_renderer())  # type: ignore[attr-defined]
        # Add a small padding (in pixels).
        pad = 4
        width = int(np.ceil(bbox.width)) + 2 * pad
        height = int(np.ceil(bbox.height)) + 2 * pad
        fig.set_size_inches(width / dpi, height / dpi)
        # Re-place the text so the padding is even.
        text.set_position((pad / width, pad / height))

        buf = io.BytesIO()
        fig.savefig(
            buf,
            format="png",
            dpi=dpi,
            transparent=background is None,
            facecolor=face,
        )
        buf.seek(0)
        from matplotlib import image as mpimg

        rgba = mpimg.imread(buf)
        # mpimg returns float in [0, 1]; convert to uint8 RGBA.
        arr = (np.clip(rgba, 0.0, 1.0) * 255).astype(np.uint8)
        if arr.ndim == 2:
            arr = np.dstack([arr, arr, arr, np.full_like(arr, 255)])
        elif arr.shape[2] == 3:
            arr = np.dstack([arr, np.full(arr.shape[:2], 255, dtype=np.uint8)])
        return arr
    finally:
        plt.close(fig)


def latex_to_array(
    latex: str,
    *,
    fontsize: int = 16,
    dpi: int = 150,
    color: str = "black",
    background: str | None = None,
) -> np.ndarray:
    """Render a LaTeX (mathtext) string to an ``H x W x 4`` uint8 RGBA array.

    Parameters
    ----------
    latex:
        The LaTeX string (without the surrounding ``$ ... $``).
    fontsize:
        Font size in points.
    dpi:
        Output DPI. Higher = larger image at the same physical size.
    color:
        Foreground color, any matplotlib color spec.
    background:
        Background color. ``None`` (default) yields a fully transparent
        background.

    Returns
    -------
    np.ndarray
        Image as ``(H, W, 4)`` uint8 RGBA.
    """

    if not latex:
        # Return a 1x1 fully transparent pixel so callers always get a valid array.
        return np.zeros((1, 1, 4), dtype=np.uint8)

    rows = _strip_alignment_env(latex)
    if len(rows) == 1:
        return _render_with_matplotlib(
            rows[0], fontsize=fontsize, dpi=dpi, color=color, background=background
        )

    images: list[np.ndarray] = []
    for row in rows:
        try:
            img = _render_with_matplotlib(
                row, fontsize=fontsize, dpi=dpi, color=color, background=background
            )
        except Exception:
            # Skip rows mathtext can't parse rather than failing the whole panel.
            continue
        images.append(img)
    if not images:
        return np.zeros((1, 1, 4), dtype=np.uint8)

    pad = 4
    width = max(img.shape[1] for img in images)
    height = sum(img.shape[0] for img in images) + pad * (len(images) - 1)
    canvas = np.zeros((height, width, 4), dtype=np.uint8)
    if background is not None:
        # Opaque background — fill before pasting.
        canvas[..., :3] = 255
        canvas[..., 3] = 255
    y = 0
    for img in images:
        h, w, _ = img.shape
        canvas[y : y + h, 0:w] = img
        y += h + pad
    return canvas


def latex_to_qimage(
    latex: str,
    *,
    fontsize: int = 16,
    dpi: int = 150,
    color: str = "black",
    background: str | None = None,
) -> "QImage":
    """Render a LaTeX (mathtext) string to a ``QImage`` for Qt widgets.

    Raises
    ------
    RuntimeError
        If PySide6 is not importable in the current environment.
    """

    try:
        from PySide6.QtGui import QImage
    except Exception as exc:  # pragma: no cover - exercised only without PySide6
        raise RuntimeError("PySide6 is required for latex_to_qimage()") from exc

    arr = latex_to_array(
        latex, fontsize=fontsize, dpi=dpi, color=color, background=background
    )
    h, w, _ = arr.shape
    # QImage.Format_RGBA8888 expects bytes ordered R, G, B, A — matplotlib gives us that.
    contiguous = np.ascontiguousarray(arr)
    image = QImage(contiguous.data, w, h, 4 * w, QImage.Format.Format_RGBA8888)
    # QImage doesn't copy the buffer, so detach by ``.copy()`` to keep it valid
    # after the ndarray goes out of scope.
    return image.copy()


def sympy_to_latex(expr: Any) -> str:
    """Convenience wrapper around :func:`sympy.latex` with display defaults.

    If ``expr`` is already a string it is returned unchanged.
    """

    if isinstance(expr, str):
        return expr
    try:
        import sympy
    except Exception as exc:  # pragma: no cover - sympy is a hard runtime dep
        raise RuntimeError("sympy is required for sympy_to_latex()") from exc
    return sympy.latex(expr)
