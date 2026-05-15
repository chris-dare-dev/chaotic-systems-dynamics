"""Tests for the LaTeX rendering helpers."""

from __future__ import annotations

import numpy as np

from chaotic_systems.visualization.latex import latex_to_array, sympy_to_latex


def test_latex_to_array_returns_rgba() -> None:
    arr = latex_to_array(r"\dot{x} = \sigma(y - x)")
    assert arr.ndim == 3
    assert arr.shape[2] == 4
    assert arr.dtype == np.uint8
    # Some pixels should be non-transparent.
    assert (arr[..., 3] > 0).any()


def test_latex_to_array_empty_string() -> None:
    arr = latex_to_array("")
    assert arr.shape == (1, 1, 4)


def test_sympy_to_latex_passthrough() -> None:
    assert sympy_to_latex(r"\alpha + \beta") == r"\alpha + \beta"


def test_sympy_to_latex_expression() -> None:
    import sympy as sp

    x, y = sp.symbols("x y")
    expr = sp.diff(sp.sin(x) * y, x)
    out = sympy_to_latex(expr)
    assert isinstance(out, str)
    assert "y" in out and "cos" in out
