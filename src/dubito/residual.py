"""Residual evaluation of nonlinear verification IR. No solver import."""

from __future__ import annotations

from typing import Mapping

from dubito.expr import compile_expr
from dubito.model import CheckResult, ConstraintViolation, Tolerances
from dubito.numeric import as_number, nearest_int
from dubito.problem import ProblemSpec, ResidualConstraint, as_residual_ir


def evaluate_residual(
    problem: ProblemSpec, assignment: Mapping[str, float], tol: Tolerances
) -> CheckResult:
    ir = as_residual_ir(problem)
    if ir is None:
        raise ValueError(f"problem {problem.id} has no residual verification IR")
    violations: list[ConstraintViolation] = []
    missing = [name for name in problem.variables if name not in assignment]
    for name in missing:
        violations.append(
            ConstraintViolation(name=f"missing:{name}", violation=1.0, detail="assignment missing variable")
        )
    if missing:
        return CheckResult(feasible=False, objective=None, violations=violations, integrality_ok=False)

    values = {name: as_number(assignment[name]) for name in problem.variables}
    integrality_ok = True
    for name, spec in problem.variables.items():
        raw = values[name]
        if spec.kind in {"integer", "binary"} and nearest_int(raw, tol) is None:
            integrality_ok = False
            violations.append(
                ConstraintViolation(
                    name=f"integrality:{name}",
                    violation=abs(raw - round(raw)),
                    detail=f"{name}={raw} is not integer",
                )
            )
        if spec.lower is not None and raw < float(spec.lower) - tol.primal_feasibility:
            violations.append(
                ConstraintViolation(
                    name=f"bound:{name}",
                    violation=float(spec.lower) - raw,
                    detail=f"{name}={raw} below lower bound",
                )
            )
        if spec.upper is not None and raw > float(spec.upper) + tol.primal_feasibility:
            violations.append(
                ConstraintViolation(
                    name=f"bound:{name}",
                    violation=raw - float(spec.upper),
                    detail=f"{name}={raw} above upper bound",
                )
            )

    names = problem.variable_names
    for constraint in ir.constraints:
        residual = _constraint_residual(constraint, values, names, tol)
        if residual > tol.primal_feasibility:
            violations.append(
                ConstraintViolation(
                    name=constraint.name,
                    violation=residual,
                    detail=f"{constraint.name} residual {residual} ({constraint.op} {constraint.rhs})",
                )
            )
    objective = compile_expr(ir.objective_expr, names)(values)
    return CheckResult(
        feasible=not violations,
        objective=float(objective),
        violations=violations,
        integrality_ok=integrality_ok,
    )


def _constraint_residual(
    constraint: ResidualConstraint,
    values: Mapping[str, float],
    names: tuple[str, ...],
    tol: Tolerances,
) -> float:
    del tol
    lhs = compile_expr(constraint.expr, names)(values)
    rhs = float(constraint.rhs)
    if constraint.op == "<=":
        return max(0.0, lhs - rhs)
    if constraint.op == ">=":
        return max(0.0, rhs - lhs)
    return abs(lhs - rhs)
