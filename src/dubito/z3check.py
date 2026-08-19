from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from z3 import And, ArithRef, BoolRef, Int, Optimize, Real, Solver, sat, unknown, unsat

from dubito.numeric import as_number, nearest_int
from dubito.model import CheckResult, ConstraintViolation, Tolerances


@dataclass
class Z3CheckResult:
    feasible: bool
    status: str
    model: dict[str, float] | None
    detail: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "feasible": self.feasible,
            "status": self.status,
            "model": self.model,
            "detail": self.detail,
        }


class Z3Spec:
    """Independent verification-layer encoding. Must not import solver formulations."""

    problem_id: str
    variables: tuple[str, ...]

    def encode(self) -> tuple[Solver, dict[str, ArithRef]]:
        raise NotImplementedError

    def check_assignment(
        self, assignment: Mapping[str, float], tol: Tolerances
    ) -> CheckResult:
        solver, var_map = self.encode()
        violations: list[ConstraintViolation] = []
        assumptions: list[BoolRef] = []
        for name, z3var in var_map.items():
            if name not in assignment:
                violations.append(
                    ConstraintViolation(name=f"missing:{name}", violation=1.0, detail="assignment missing variable")
                )
                continue
            value = as_number(assignment[name])
            as_int = nearest_int(value, tol)
            if as_int is not None:
                assumptions.append(z3var == as_int)
            else:
                # Fall back to a small rational box around the float.
                # Exact reals for arbitrary floats are not the Phase 1 target.
                assumptions.append(And(z3var >= value - tol.primal_feasibility, z3var <= value + tol.primal_feasibility))
        if violations:
            return CheckResult(feasible=False, objective=None, violations=violations, integrality_ok=False)
        result = solver.check(*assumptions)
        if result == sat:
            return CheckResult(feasible=True, objective=None, violations=[], integrality_ok=True)
        if result == unsat:
            violations.append(
                ConstraintViolation(
                    name="z3",
                    violation=1.0,
                    detail="assignment is unsat against the independent Z3 encoding",
                )
            )
            return CheckResult(feasible=False, objective=None, violations=violations, integrality_ok=True)
        return CheckResult(
            feasible=False,
            objective=None,
            violations=[
                ConstraintViolation(name="z3", violation=1.0, detail=f"Z3 returned {result}")
            ],
            integrality_ok=True,
        )

    def check_feasibility(self) -> Z3CheckResult:
        solver, var_map = self.encode()
        result = solver.check()
        if result == sat:
            model = solver.model()
            decoded: dict[str, float] = {}
            for name, var in var_map.items():
                val = model.eval(var)
                try:
                    decoded[name] = float(val.as_long())
                except AttributeError:
                    decoded[name] = float(str(val.as_decimal(12)).rstrip("?"))
            return Z3CheckResult(feasible=True, status="sat", model=decoded)
        if result == unsat:
            return Z3CheckResult(feasible=False, status="unsat", model=None)
        return Z3CheckResult(feasible=False, status=str(result), model=None, detail="unknown")


def int_var(name: str) -> ArithRef:
    return Int(name)


def real_var(name: str) -> ArithRef:
    return Real(name)


def optimize() -> Optimize:
    return Optimize()


def is_sat(result: object) -> bool:
    return result == sat


def is_unknown(result: object) -> bool:
    return result == unknown
