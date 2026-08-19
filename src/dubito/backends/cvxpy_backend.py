from __future__ import annotations

import time
from abc import abstractmethod
from typing import Mapping

import cvxpy as cp

from dubito.numeric import as_number, bound_violation, nearest_int
from dubito.model import (
    CheckResult,
    ConstraintViolation,
    Formulation,
    Sense,
    SolveResult,
    SolveStatus,
    Tolerances,
)

_STATUS: dict[str, SolveStatus] = {
    cp.OPTIMAL: "optimal",
    cp.OPTIMAL_INACCURATE: "optimal",
    cp.INFEASIBLE: "infeasible",
    cp.INFEASIBLE_INACCURATE: "infeasible",
    cp.UNBOUNDED: "unbounded",
    cp.UNBOUNDED_INACCURATE: "unbounded",
}


class CvxpyFormulation(Formulation):
    """Runtime adapter. Subclasses independently write `_problem()`."""

    sense: Sense = "max"
    solver = cp.GLPK_MI

    @abstractmethod
    def _problem(self) -> tuple[cp.Problem, dict[str, cp.Variable]]:
        raise NotImplementedError

    def solve(self) -> SolveResult:
        started = time.perf_counter()
        try:
            problem, var_map = self._problem()
            problem.solve(solver=self.solver, verbose=False)
        except Exception as exc:  # noqa: BLE001 — solver failures become score errors
            return SolveResult(
                solver=self.name,
                status="error",
                assignment={},
                objective=None,
                runtime_ms=(time.perf_counter() - started) * 1000,
                error=str(exc),
            )
        status = _STATUS.get(problem.status, "unknown")
        assignment: dict[str, float] = {}
        if status in {"optimal", "feasible"}:
            assignment = {
                name: as_number(var.value) for name, var in var_map.items() if var.value is not None
            }
        objective = None
        if problem.objective.value is not None:
            objective = as_number(problem.objective.value)
        return SolveResult(
            solver=self.name,
            status=status,
            assignment=assignment,
            objective=objective,
            runtime_ms=(time.perf_counter() - started) * 1000,
        )

    def check(self, assignment: Mapping[str, float], tol: Tolerances) -> CheckResult:
        problem, var_map = self._problem()
        violations: list[ConstraintViolation] = []
        integrality_ok = True
        for name, var in var_map.items():
            if name not in assignment:
                violations.append(
                    ConstraintViolation(name=f"missing:{name}", violation=1.0, detail="assignment missing variable")
                )
                continue
            value = as_number(assignment[name])
            var.value = value
            lower = _var_lower(var)
            upper = _var_upper(var)
            bound = bound_violation(value, lower, upper)
            if bound > tol.primal_feasibility:
                violations.append(
                    ConstraintViolation(
                        name=f"bound:{name}",
                        violation=bound,
                        detail=f"{name}={value} outside [{lower}, {upper}]",
                    )
                )
            if _is_integer_var(var) and nearest_int(value, tol) is None:
                integrality_ok = False
                violations.append(
                    ConstraintViolation(
                        name=f"integrality:{name}",
                        violation=abs(value - round(value)),
                        detail=f"{name}={value} is not integer",
                    )
                )
        for index, constraint in enumerate(problem.constraints):
            try:
                viol = as_number(constraint.violation())
            except Exception as exc:  # noqa: BLE001
                viol = float("inf")
                violations.append(
                    ConstraintViolation(
                        name=f"c{index}",
                        violation=viol,
                        detail=f"could not evaluate: {exc}",
                    )
                )
                continue
            if viol > tol.primal_feasibility:
                violations.append(
                    ConstraintViolation(
                        name=constraint.name() or f"c{index}",
                        violation=viol,
                        detail=str(constraint),
                    )
                )
        objective = None
        try:
            if problem.objective.value is not None:
                objective = as_number(problem.objective.value)
        except Exception:  # noqa: BLE001
            objective = None
        feasible = not violations
        return CheckResult(
            feasible=feasible,
            objective=objective,
            violations=violations,
            integrality_ok=integrality_ok,
        )


def _is_integer_var(var: cp.Variable) -> bool:
    attrs = var.attributes
    return bool(attrs.get("integer") or attrs.get("boolean"))


def _var_lower(var: cp.Variable) -> float | None:
    attrs = var.attributes
    if attrs.get("boolean") or attrs.get("nonneg"):
        return 0.0
    bounds = attrs.get("bounds")
    if not bounds:
        return None
    lower = bounds[0]
    if lower is None:
        return None
    return as_number(lower)


def _var_upper(var: cp.Variable) -> float | None:
    attrs = var.attributes
    if attrs.get("boolean"):
        return 1.0
    if attrs.get("nonpos"):
        return 0.0
    bounds = attrs.get("bounds")
    if not bounds:
        return None
    upper = bounds[1]
    if upper is None:
        return None
    return as_number(upper)
