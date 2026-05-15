"""Tests for the LaTeX rendering helpers."""

from __future__ import annotations

import numpy as np

from chaotic_systems.visualization.latex import (
    latex_to_array,
    sanitize_for_mathtext,
    sympy_to_latex,
)


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


def test_sanitize_rewrites_tfrac_to_frac() -> None:
    """\\tfrac is unsupported by mathtext; we substitute \\frac without
    accidentally producing the form-feed character (the original
    ``re.sub`` based implementation produced ``\\x0crac`` because Python
    interprets ``\\f`` in regex replacement strings)."""

    src = r"T = \tfrac{1}{2}(m_1+m_2) l_1^2"
    out = sanitize_for_mathtext(src)
    assert "\\tfrac" not in out
    assert "\\frac" in out
    assert "\x0c" not in out  # no form-feed contamination


def test_sanitize_idempotent() -> None:
    src = r"\frac{1}{2} + \alpha"
    assert sanitize_for_mathtext(src) == src


def test_latex_to_array_renders_double_pendulum_kinetic_energy() -> None:
    """End-to-end regression for the original DoublePendulum crash."""

    src = (
        r"T = \tfrac{1}{2}(m_1+m_2) l_1^2 \dot\theta_1^2 "
        r"+ \tfrac{1}{2} m_2 l_2^2 \dot\theta_2^2"
    )
    arr = latex_to_array(src, fontsize=13, dpi=120, color="#c0caf5")
    assert arr.ndim == 3
    # The rendered image should have meaningful width — a tiny one-pixel
    # image would indicate the fallback message rendered instead.
    assert arr.shape[1] > 100


def test_sympy_to_latex_expression() -> None:
    import sympy as sp

    x, y = sp.symbols("x y")
    expr = sp.diff(sp.sin(x) * y, x)
    out = sympy_to_latex(expr)
    assert isinstance(out, str)
    assert "y" in out and "cos" in out
