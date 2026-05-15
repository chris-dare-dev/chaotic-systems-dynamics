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
- :func:`latex_to_array` — render LaTeX to an RGBA ndarray (LRU-cached).
- :func:`latex_to_qimage` — render LaTeX to a ``QImage`` (raises ``RuntimeError``
  if PySide6 is unavailable in the current environment).
- :func:`sympy_to_latex` — wrap :func:`sympy.latex` with sane defaults.
"""

from __future__ import annotations

import io
import re
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from PySide6.QtGui import QImage

__all__ = [
    "latex_to_array",
    "latex_to_qimage",
    "sanitize_for_mathtext",
    "sympy_to_latex",
]


# Macros matplotlib's mathtext does NOT understand but for which a near-
# equivalent macro exists. We pre-process LaTeX strings to swap them for
# the mathtext-friendly form so the equation panel doesn't render raw
# ``ParseFatalException`` text.
#
# This map covers the substitutions identified in the catalog audit
# (DoublePendulum / HenonHeiles / Chua all use ``\tfrac``). ``\dfrac`` is
# included pre-emptively since SymPy emits it for display-style
# fractions. ``\mathrm`` and ``\operatorname`` are tolerated by mathtext
# (it treats them as upright groups), but we normalise them here so they
# render consistently with the rest of the panel.
_MATHTEXT_MACRO_SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    (r"\tfrac", r"\frac"),
    (r"\dfrac", r"\frac"),
    (r"\nicefrac", r"\frac"),
)


def sanitize_for_mathtext(latex: str) -> str:
    """Return ``latex`` with mathtext-unsupported macros rewritten in place.

    Matplotlib's mathtext engine is a strict subset of LaTeX — display-style
    fraction macros (``\\tfrac`` / ``\\dfrac`` / ``\\nicefrac``) raise
    ``ParseFatalException``. We pre-process the input so the user sees a
    rendered equation instead of an exception traceback. The replacements
    are conservative whole-word swaps that preserve the surrounding braces.

    The function is idempotent: passing already-clean LaTeX returns it
    unchanged.
    """

    out = latex
    for old, new in _MATHTEXT_MACRO_SUBSTITUTIONS:
        # \tfrac etc. — boundary on a non-letter ensures we don't catch
        # e.g. \tfraction (no such macro, but it's defensive).
        #
        # ``re.sub`` interprets backslash sequences in the *replacement*
        # string (``\f`` becomes form-feed, ``\1``-``\9`` become group
        # back-refs). Passing the replacement as a lambda sidesteps that
        # — the callable's return value is taken literally.
        replacement_value = new
        out = re.sub(
            re.escape(old) + r"(?=[^A-Za-z])",
            lambda _m, r=replacement_value: r,
            out,
        )
        # If the macro is at the very end of the string (no trailing
        # character), the lookahead above won't fire; handle that case.
        if out.endswith(old):
            out = out[: -len(old)] + new
    return out


# Environments whose rows really ARE separately-renderable equations.
# Matrix environments (`matrix`, `pmatrix`, `bmatrix`) are intentionally
# excluded — their rows are columns of a single math object, not a stack
# of equations, and per-row rendering produces visual garbage.
_ALIGN_ENVS = (
    "aligned",
    "align",
    "align*",
    "cases",
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
    rows = [row.strip() for row in body.split(r"\\")]
    rows = [r.replace("&", "") for r in rows if r]
    return rows


_FALLBACK_MESSAGE = r"\text{renderer cannot display this expression}"


def _render_with_matplotlib(
    latex: str,
    *,
    fontsize: int,
    dpi: int,
    color: str,
    background: str | None,
) -> np.ndarray:
    """Internal: render via matplotlib's mathtext to an RGBA buffer.

    Single draw pass: we configure the figure to size itself to its
    content via ``bbox_inches="tight"`` on ``savefig`` rather than the
    historical draw-then-resize-then-redraw sequence.

    Sanitisation
    ------------
    Display-style fraction macros (``\\tfrac`` / ``\\dfrac``) are silently
    rewritten to ``\\frac`` so the equation panel always renders the
    equation rather than dumping a ``ParseFatalException`` into the GUI.
    If a sanitised string still fails to parse we fall back to a clean
    "cannot display" message instead of raising.
    """

    import matplotlib

    # Use a non-interactive backend so this works headless. We don't
    # ``matplotlib.use(...)`` after a Qt application has been built because
    # Qt has already locked in QtAgg; using a stand-alone ``Figure`` plus
    # ``FigureCanvasAgg`` lets us render off-screen regardless of the
    # interactive backend matplotlib is using elsewhere in the process.
    matplotlib.use("Agg", force=False)
    from matplotlib import image as mpimg
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    sanitized = sanitize_for_mathtext(latex)
    attempts = [sanitized]
    if sanitized != latex:
        # The original might still parse on some matplotlib versions; we
        # try the sanitised form first because it's the conservative choice.
        attempts.append(latex)
    attempts.append(_FALLBACK_MESSAGE)

    last_exc: Exception | None = None
    for attempt in attempts:
        fig = Figure(figsize=(0.5, 0.5), dpi=dpi)
        # Bind a headless Agg canvas explicitly — without this, calling
        # ``savefig`` on a bare Figure in a Qt-bound process can route
        # through the QtAgg canvas which raises on a worker / background
        # thread or before the Qt event loop has spun up.
        FigureCanvasAgg(fig)
        try:
            if background is None:
                fig.patch.set_alpha(0.0)
                face: Any = (0.0, 0.0, 0.0, 0.0)
            else:
                fig.patch.set_alpha(1.0)
                fig.patch.set_facecolor(background)
                face = background
            fig.text(
                0.5,
                0.5,
                f"${attempt}$",
                fontsize=fontsize,
                color=color,
                verticalalignment="center",
                horizontalalignment="center",
            )

            buf = io.BytesIO()
            fig.savefig(
                buf,
                format="png",
                dpi=dpi,
                transparent=background is None,
                facecolor=face,
                bbox_inches="tight",
                pad_inches=0.05,
            )
            buf.seek(0)
            rgba = mpimg.imread(buf)
            arr = (np.clip(rgba, 0.0, 1.0) * 255).astype(np.uint8)
            if arr.ndim == 2:
                arr = np.dstack([arr, arr, arr, np.full_like(arr, 255)])
            elif arr.shape[2] == 3:
                arr = np.dstack(
                    [arr, np.full(arr.shape[:2], 255, dtype=np.uint8)]
                )
            return arr
        except Exception as exc:  # noqa: BLE001 - we re-raise below if all fail
            last_exc = exc
            continue
        finally:
            # ``Figure`` from ``matplotlib.figure`` doesn't need ``plt.close``;
            # GC will reclaim it. But we explicitly clear the artists so the
            # backend's text caches don't keep references alive.
            try:
                fig.clf()
            except Exception:  # pragma: no cover - defensive
                pass
    # Even the fallback message failed — extremely unlikely (it's plain
    # ASCII inside \text), but raise something informative if it does.
    raise RuntimeError(
        "mathtext could not render any variant of the supplied LaTeX"
    ) from last_exc


def _cache_key(
    latex: str,
    fontsize: int,
    dpi: int,
    color: str,
    background: str | None,
) -> tuple[str, int, int, str, str | None]:
    return (latex, fontsize, dpi, color, background)


@lru_cache(maxsize=64)
def _render_cached(
    key: tuple[str, int, int, str, str | None],
) -> tuple[bytes, tuple[int, int, int]]:
    """LRU-cached render. Returns ``(bytes, shape)``.

    We store bytes + shape rather than an ``ndarray`` directly because
    ``lru_cache`` retains references to its values; ndarrays held by the
    cache would prevent the renderer from releasing memory if a caller
    mutated the returned buffer. Round-tripping through bytes is also a
    convenient pickle-safe representation.
    """

    latex, fontsize, dpi, color, background = key
    arr = _render_with_matplotlib(
        latex, fontsize=fontsize, dpi=dpi, color=color, background=background
    )
    return arr.tobytes(), arr.shape  # type: ignore[return-value]


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
        return np.zeros((1, 1, 4), dtype=np.uint8)

    rows = _strip_alignment_env(latex)
    if len(rows) == 1:
        data, shape = _render_cached(
            _cache_key(rows[0], fontsize, dpi, color, background)
        )
        return np.frombuffer(data, dtype=np.uint8).reshape(shape).copy()

    images: list[np.ndarray] = []
    for row in rows:
        try:
            data, shape = _render_cached(
                _cache_key(row, fontsize, dpi, color, background)
            )
        except Exception:
            continue
        images.append(np.frombuffer(data, dtype=np.uint8).reshape(shape).copy())
    if not images:
        return np.zeros((1, 1, 4), dtype=np.uint8)

    pad = 4
    width = max(img.shape[1] for img in images)
    height = sum(img.shape[0] for img in images) + pad * (len(images) - 1)
    canvas = np.zeros((height, width, 4), dtype=np.uint8)
    if background is not None:
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
) -> QImage:
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
    contiguous = np.ascontiguousarray(arr)
    image = QImage(contiguous.data, w, h, 4 * w, QImage.Format.Format_RGBA8888)
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
