from __future__ import annotations

from fractions import Fraction
from typing import Mapping

from dubito.model import CheckResult, ConstraintViolation, Tolerances
from dubito.numeric import as_number, nearest_int
from dubito.problem import LinearConstraint, ProblemSpec, VerificationIR, VariableSpec, as_linear_ir, as_residual_ir


def assignment_values(
    problem: ProblemSpec, assignment: Mapping[str, float], tol: Tolerances
) -> dict[str, Fraction]:
    values: dict[str, Fraction] = {}
    for name, spec in problem.variables.items():
        if name not in assignment:
            raise KeyError(name)
        raw = as_number(assignment[name])
        if spec.kind in {"integer", "binary"}:
            rounded = nearest_int(raw, tol)
            if rounded is None:
                values[name] = Fraction(raw).limit_denominator()
            else:
                values[name] = Fraction(rounded)
        else:
            values[name] = Fraction(raw).limit_denominator(10_000_000)
    return values


def linear_value(terms: Mapping[str, Fraction], values: Mapping[str, Fraction]) -> Fraction:
    total = Fraction(0)
    for name, coeff in terms.items():
        total += coeff * values[name]
    return total


def constraint_residual(constraint: LinearConstraint, values: Mapping[str, Fraction]) -> Fraction:
    lhs = linear_value(constraint.terms, values)
    if constraint.op == "<=":
        return max(Fraction(0), lhs - constraint.rhs)
    if constraint.op == ">=":
        return max(Fraction(0), constraint.rhs - lhs)
    return abs(lhs - constraint.rhs)


def bound_residual(spec: VariableSpec, value: Fraction) -> Fraction:
    viol = Fraction(0)
    if spec.lower is not None and value < spec.lower:
        viol = max(viol, spec.lower - value)
    if spec.upper is not None and value > spec.upper:
        viol = max(viol, value - spec.upper)
    if spec.kind == "binary" and value not in {Fraction(0), Fraction(1)}:
        viol = max(viol, min(abs(value), abs(value - 1)))
    return viol


def evaluate_ir(
    problem: ProblemSpec, assignment: Mapping[str, float], tol: Tolerances
) -> CheckResult:
    """Exact (rational) residual check of the verification IR. No Z3."""

    ir = _require_ir(problem)
    violations: list[ConstraintViolation] = []
    integrality_ok = True
    missing = [name for name in problem.variables if name not in assignment]
    for name in missing:
        violations.append(
            ConstraintViolation(name=f"missing:{name}", violation=1.0, detail="assignment missing variable")
        )
    if missing:
        return CheckResult(feasible=False, objective=None, violations=violations, integrality_ok=False)
    values = assignment_values(problem, assignment, tol)
    for name, spec in problem.variables.items():
        raw = as_number(assignment[name])
        if spec.kind in {"integer", "binary"} and nearest_int(raw, tol) is None:
            integrality_ok = False
            violations.append(
                ConstraintViolation(
                    name=f"integrality:{name}",
                    violation=abs(raw - round(raw)),
                    detail=f"{name}={raw} is not integer",
                )
            )
        bound = bound_residual(spec, values[name])
        if bound > 0:
            violations.append(
                ConstraintViolation(
                    name=f"bound:{name}",
                    violation=float(bound),
                    detail=f"{name}={values[name]} outside [{spec.lower}, {spec.upper}]",
                )
            )
    for constraint in ir.constraints:
        residual = constraint_residual(constraint, values)
        if residual > 0:
            violations.append(
                ConstraintViolation(
                    name=constraint.name,
                    violation=float(residual),
                    detail=f"{constraint.name} residual {residual} ({constraint.op} {constraint.rhs})",
                )
            )
    objective = float(linear_value(ir.objective, values))
    return CheckResult(
        feasible=not violations,
        objective=objective,
        violations=violations,
        integrality_ok=integrality_ok,
    )


def evaluate_witness(
    problem: ProblemSpec, assignment: Mapping[str, float], tol: Tolerances
) -> CheckResult | None:
    if as_linear_ir(problem) is not None:
        return evaluate_ir(problem, assignment, tol)
    if as_residual_ir(problem) is not None:
        from dubito.residual import evaluate_residual

        return evaluate_residual(problem, assignment, tol)
    return None


def _require_ir(problem: ProblemSpec) -> VerificationIR:
    ir = as_linear_ir(problem)
    if ir is None:
        raise ValueError(f"problem {problem.id} has no linear verification IR")
    return ir
