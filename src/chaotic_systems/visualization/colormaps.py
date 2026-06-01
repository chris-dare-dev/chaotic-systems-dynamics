r"""Central colormap registry for density / attractor-art rendering.

A single lookup point so the GUI and the density renderer never reach for
``matplotlib.colormaps[...]`` (or the deprecated ``cm.get_cmap``) inline. The
registry resolves a stable set of names to matplotlib :class:`~matplotlib.colors.Colormap`
objects:

- **magma**, **inferno** — matplotlib's perceptually-uniform sequential maps.
  Both start at near-black, which is exactly why an attractor-density image on a
  black background reads cleanly (empty/zero-count cells map to ``cmap(0) ~ black``).
- **conradi** — a custom black -> ``#ffe100`` (warm yellow) ramp matching the
  palette in Simone Conradi's ``Nice_orbits.ipynb`` density renders.

This is CSC-009 of docs/proposals/conradi-attractor-panel-2026-05-31.md.

Scope note: the proposal also referenced "already-registered ``ember`` / ``ice``
ramps" to surface, but no such registry or ramps existed in the codebase (the
sourcing brief was inaccurate) — there was no central colormap module at all.
This module therefore *creates* the registry with the genuinely-sourced entries
(magma/inferno per Smith & van der Walt; the Conradi ramp per the notebook)
rather than inventing two unspecified ramps. ``colorcet`` (a closer "fire"
match, CC-BY-4.0) is intentionally not a dependency — matplotlib suffices.

References
----------
- N. Smith & S. van der Walt, *A Better Default Colormap for Matplotlib*,
  SciPy 2015 (the viridis/magma/inferno/plasma family; perceptually uniform,
  near-black low end). https://www.youtube.com/watch?v=xAoljeRJ3lU
- Simone Conradi, ``Nice_orbits.ipynb``,
  https://github.com/profConradi/Python_Simulations (the custom black->#ffe100
  density palette this module reproduces as ``conradi``).
"""

from __future__ import annotations

import matplotlib
from matplotlib.colors import Colormap, LinearSegmentedColormap

# The signature warm-yellow endpoint of Conradi's density palette.
_CONRADI_YELLOW: str = "#ffe100"

# Registry name for the custom ramp.
_CONRADI_NAME: str = "conradi"

# Built-in matplotlib maps surfaced through this registry. Listed in the order
# the GUI picker should show them; "conradi" is prepended at build time.
_BUILTIN_NAMES: tuple[str, ...] = ("magma", "inferno")


def _build_conradi_cmap() -> LinearSegmentedColormap:
    """Construct the black -> #ffe100 ramp used by Conradi's density renders.

    A two-stop linear segment from pure black to warm yellow. Pure black at
    the low end means zero-count cells vanish into a black background, the same
    convention the magma/inferno maps give for free.
    """
    return LinearSegmentedColormap.from_list(
        _CONRADI_NAME, ["#000000", _CONRADI_YELLOW]
    )


# Built once at import. Maps name -> Colormap instance. The custom ramp is
# created here; the matplotlib built-ins are resolved lazily in ``get`` so we
# never hold stale references if matplotlib re-registers them.
_CUSTOM: dict[str, Colormap] = {_CONRADI_NAME: _build_conradi_cmap()}


def available() -> list[str]:
    """Return the registry's colormap names in GUI display order.

    The custom ``conradi`` ramp first, then the perceptually-uniform built-ins.
    """
    return [_CONRADI_NAME, *_BUILTIN_NAMES]


def get(name: str) -> Colormap:
    """Resolve a registry name to a matplotlib :class:`~matplotlib.colors.Colormap`.

    Parameters
    ----------
    name
        One of :func:`available`.

    Raises
    ------
    KeyError
        If ``name`` is not a registered colormap. The message lists the valid
        names so a typo surfaces immediately rather than falling through to a
        matplotlib default.
    """
    if name in _CUSTOM:
        return _CUSTOM[name]
    if name in _BUILTIN_NAMES:
        return matplotlib.colormaps[name]
    raise KeyError(
        f"unknown colormap {name!r}; available: {available()}"
    )


__all__ = ["available", "get"]
