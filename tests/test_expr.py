from __future__ import annotations

import pytest

from dubito.expr import ExprError, compile_expr


def test_rosenbrock_expr_is_zero_at_minimizer() -> None:
    fn = compile_expr("(1 - x)**2 + 100 * (y - x**2)**2", ("x", "y"))
    assert fn({"x": 1.0, "y": 1.0}) == pytest.approx(0.0)
    assert fn({"x": 0.0, "y": 0.0}) == pytest.approx(1.0)


def test_allows_abs_and_sqrt() -> None:
    fn = compile_expr("abs(x) + sqrt(y)", ("x", "y"))
    assert fn({"x": -3.0, "y": 4.0}) == pytest.approx(5.0)


def test_rejects_calls_and_imports() -> None:
    with pytest.raises(ExprError):
        compile_expr("__import__('os').system('true')", ("x",))
    with pytest.raises(ExprError):
        compile_expr("lambda x: x", ("x",))
    with pytest.raises(ExprError):
        compile_expr("[x]", ("x",))
    with pytest.raises(ExprError):
        compile_expr("sin(x)", ("x",))


def test_rejects_large_exponent() -> None:
    with pytest.raises(ExprError, match="exponent"):
        compile_expr("x ** 9", ("x",))


def test_unknown_name_is_error() -> None:
    with pytest.raises(ExprError, match="unknown name"):
        compile_expr("x + z", ("x", "y"))
