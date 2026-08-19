from __future__ import annotations

from dubito.model import Tolerances


def as_number(value: object) -> float:
    return float(value)


def numbers_close(a: float | None, b: float | None, tol: Tolerances) -> bool:
    if a is None or b is None:
        return False
    scale = max(1.0, abs(a), abs(b))
    return abs(a - b) <= max(tol.objective_abs, tol.objective_rel * scale)


def nearest_int(value: float, tol: Tolerances) -> int | None:
    rounded = round(value)
    if abs(value - rounded) <= tol.integrality:
        return int(rounded)
    return None


def bound_violation(value: float, lower: float | None, upper: float | None) -> float:
    viol = 0.0
    if lower is not None and value < lower:
        viol = max(viol, lower - value)
    if upper is not None and value > upper:
        viol = max(viol, value - upper)
    return viol
