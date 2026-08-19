from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from z3 import And, ArithRef, BoolRef, Int, Optimize, Real, RealVal, Solver, sat, unknown, unsat

from dubito.ir import evaluate_ir
from dubito.numeric import as_number, nearest_int
from dubito.model import CheckResult, ConstraintViolation, Tolerances
from dubito.problem import ProblemSpec, VerificationIR, as_linear_ir


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


class LinearZ3Spec(Z3Spec):
    """Z3 encoding of a ProblemSpec verification IR. Not a solver formulation."""

    def __init__(self, problem: ProblemSpec) -> None:
        ir = as_linear_ir(problem)
        if ir is None:
            raise ValueError(f"problem {problem.id} has no linear verification IR")
        self.problem = problem
        self.problem_id = problem.id
        self.variables = problem.variable_names

    def encode(self) -> tuple[Solver, dict[str, ArithRef]]:
        solver = Solver()
        var_map: dict[str, ArithRef] = {}
        for name, spec in self.problem.variables.items():
            if spec.kind in {"integer", "binary"}:
                z3var: ArithRef = Int(name)
            else:
                z3var = Real(name)
            var_map[name] = z3var
            if spec.lower is not None:
                solver.add(z3var >= _z3_num(spec.lower))
            if spec.upper is not None:
                solver.add(z3var <= _z3_num(spec.upper))
        ir = as_linear_ir(self.problem)
        assert ir is not None
        for constraint in ir.constraints:
            expr = None
            for var_name, coeff in constraint.terms.items():
                term = _z3_num(coeff) * var_map[var_name]
                expr = term if expr is None else expr + term
            assert expr is not None
            rhs = _z3_num(constraint.rhs)
            if constraint.op == "<=":
                solver.add(expr <= rhs)
            elif constraint.op == ">=":
                solver.add(expr >= rhs)
            else:
                solver.add(expr == rhs)
        return solver, var_map

    def check_assignment(
        self, assignment: Mapping[str, float], tol: Tolerances
    ) -> CheckResult:
        ir_check = evaluate_ir(self.problem, assignment, tol)
        z3_check = super().check_assignment(assignment, tol)
        violations = list(ir_check.violations)
        if ir_check.feasible and not z3_check.feasible:
            violations.extend(z3_check.violations)
        return CheckResult(
            feasible=ir_check.feasible and z3_check.feasible,
            objective=ir_check.objective,
            violations=violations,
            integrality_ok=ir_check.integrality_ok,
        )


def _z3_num(value: object) -> ArithRef | int:
    from fractions import Fraction

    frac = value if isinstance(value, Fraction) else Fraction(str(value))
    if frac.denominator == 1:
        return int(frac.numerator)
    return RealVal(frac.numerator) / RealVal(frac.denominator)


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
