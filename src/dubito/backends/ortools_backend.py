from __future__ import annotations

import math
import time
from abc import abstractmethod
from typing import Mapping

from ortools.linear_solver import pywraplp

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

_STATUS: dict[int, SolveStatus] = {
    pywraplp.Solver.OPTIMAL: "optimal",
    pywraplp.Solver.FEASIBLE: "feasible",
    pywraplp.Solver.INFEASIBLE: "infeasible",
    pywraplp.Solver.UNBOUNDED: "unbounded",
    pywraplp.Solver.ABNORMAL: "error",
    pywraplp.Solver.NOT_SOLVED: "unknown",
}


class OrtoolsFormulation(Formulation):
    """Runtime adapter. Subclasses independently write `_build()`."""

    sense: Sense = "max"
    solver_id = "CBC"

    @abstractmethod
    def _build(self) -> tuple[pywraplp.Solver, dict[str, pywraplp.Variable]]:
        raise NotImplementedError

    def solve(self) -> SolveResult:
        started = time.perf_counter()
        try:
            solver, var_map = self._build()
            raw = solver.Solve()
        except Exception as exc:  # noqa: BLE001
            return SolveResult(
                solver=self.name,
                status="error",
                assignment={},
                objective=None,
                runtime_ms=(time.perf_counter() - started) * 1000,
                error=str(exc),
            )
        status = _STATUS.get(raw, "unknown")
        assignment: dict[str, float] = {}
        objective = None
        if status in {"optimal", "feasible"}:
            assignment = {name: var.solution_value() for name, var in var_map.items()}
            objective = solver.Objective().Value()
        return SolveResult(
            solver=self.name,
            status=status,
            assignment=assignment,
            objective=objective,
            runtime_ms=(time.perf_counter() - started) * 1000,
        )

    def check(self, assignment: Mapping[str, float], tol: Tolerances) -> CheckResult:
        solver, var_map = self._build()
        violations: list[ConstraintViolation] = []
        integrality_ok = True
        values: dict[str, float] = {}
        for name, var in var_map.items():
            if name not in assignment:
                violations.append(
                    ConstraintViolation(name=f"missing:{name}", violation=1.0, detail="assignment missing variable")
                )
                continue
            value = as_number(assignment[name])
            values[name] = value
            lower = var.lb()
            upper = var.ub()
            if math.isinf(lower):
                lower_b: float | None = None
            else:
                lower_b = lower
            if math.isinf(upper):
                upper_b: float | None = None
            else:
                upper_b = upper
            bound = bound_violation(value, lower_b, upper_b)
            if bound > tol.primal_feasibility:
                violations.append(
                    ConstraintViolation(
                        name=f"bound:{name}",
                        violation=bound,
                        detail=f"{name}={value} outside [{lower_b}, {upper_b}]",
                    )
                )
            if var.integer() and nearest_int(value, tol) is None:
                integrality_ok = False
                violations.append(
                    ConstraintViolation(
                        name=f"integrality:{name}",
                        violation=abs(value - round(value)),
                        detail=f"{name}={value} is not integer",
                    )
                )
        for index, constraint in enumerate(solver.constraints()):
            activity = 0.0
            for name, var in var_map.items():
                if name not in values:
                    continue
                activity += constraint.GetCoefficient(var) * values[name]
            viol = 0.0
            lb, ub = constraint.lb(), constraint.ub()
            if not math.isinf(lb) and activity < lb:
                viol = max(viol, lb - activity)
            if not math.isinf(ub) and activity > ub:
                viol = max(viol, activity - ub)
            if viol > tol.primal_feasibility:
                violations.append(
                    ConstraintViolation(
                        name=constraint.name() or f"c{index}",
                        violation=viol,
                        detail=f"activity={activity} bounds=[{lb}, {ub}]",
                    )
                )
        objective = None
        if len(values) == len(var_map):
            obj = solver.Objective()
            objective = obj.offset()
            for name, var in var_map.items():
                objective += obj.GetCoefficient(var) * values[name]
        feasible = not violations
        return CheckResult(
            feasible=feasible,
            objective=objective,
            violations=violations,
            integrality_ok=integrality_ok,
        )
