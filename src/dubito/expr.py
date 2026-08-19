"""Safe arithmetic expressions for residual verification IR.

Formulation modules must not import this. The YAML residual block is a witness,
not a compiler input.
"""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable, Mapping

_BINOPS: dict[type, Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_UNARY: dict[type, Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_FUNCS: dict[str, Callable[..., float]] = {
    "abs": abs,
    "sqrt": math.sqrt,
}


class ExprError(ValueError):
    """Raised when a residual expression is not in the allowed subset."""


def compile_expr(
    expr: str, names: tuple[str, ...]
) -> Callable[[Mapping[str, float]], float]:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ExprError(f"invalid expression {expr!r}: {exc}") from exc
    allowed = set(names)

    def _eval(node: ast.AST, values: Mapping[str, float]) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body, values)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in allowed:
                raise ExprError(f"unknown name {node.id!r} in {expr!r}")
            return float(values[node.id])
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            if isinstance(node.op, ast.Pow):
                exp = _eval(node.right, values)
                if abs(exp) > 8:
                    raise ExprError("exponent must have abs <= 8")
            return float(_BINOPS[type(node.op)](_eval(node.left, values), _eval(node.right, values)))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return float(_UNARY[type(node.op)](_eval(node.operand, values)))
        if isinstance(node, (ast.Attribute, ast.Subscript)):
            raise ExprError(f"disallowed syntax in {expr!r}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
                raise ExprError(f"function not allowed in {expr!r}")
            if node.keywords:
                raise ExprError("keyword arguments are not allowed")
            args = [_eval(arg, values) for arg in node.args]
            return float(_FUNCS[node.func.id](*args))
        raise ExprError(f"disallowed syntax in {expr!r}")

    try:
        _eval(tree, {name: 1.0 for name in names})
    except ExprError:
        raise
    except (ZeroDivisionError, ValueError, OverflowError):
        pass

    def compiled(values: Mapping[str, float]) -> float:
        missing = [name for name in names if name not in values]
        if missing:
            raise KeyError(missing[0])
        return _eval(tree, values)

    return compiled
