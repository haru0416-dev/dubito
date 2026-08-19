from __future__ import annotations

from typing import Mapping

from dubito.model import (
    CheckResult,
    ConstraintViolation,
    Formulation,
    Sense,
    SolveResult,
    SolveStatus,
    Tolerances,
)


class FakeFormulation(Formulation):
    """Deterministic stand-in so exchange logic can be tested without solvers."""

    def __init__(
        self,
        name: str,
        assignment: dict[str, float],
        objective: float,
        *,
        sense: Sense = "max",
        status: SolveStatus = "optimal",
        rejected: dict[tuple[float, ...], str] | None = None,
        objective_at: dict[tuple[float, ...], float] | None = None,
        error: str | None = None,
        problem_id: str = "fake",
    ) -> None:
        self.name = name
        self.variables = tuple(assignment)
        self.sense = sense
        self.problem_id = problem_id
        self._assignment = assignment
        self._objective = objective
        self._status = status
        self._rejected = rejected or {}
        self._objective_at = objective_at or {}
        self._error = error

    def solve(self) -> SolveResult:
        if self._error:
            return SolveResult(
                solver=self.name,
                status="error",
                assignment={},
                objective=None,
                runtime_ms=0.0,
                error=self._error,
            )
        return SolveResult(
            solver=self.name,
            status=self._status,
            assignment=dict(self._assignment),
            objective=self._objective,
            runtime_ms=0.0,
        )

    def check(self, assignment: Mapping[str, float], tol: Tolerances) -> CheckResult:
        key = tuple(assignment[v] for v in self.variables)
        if key in self._rejected:
            return CheckResult(
                feasible=False,
                objective=self._objective_at.get(key),
                violations=[
                    ConstraintViolation(name="fake", violation=1.0, detail=self._rejected[key])
                ],
            )
        obj = self._objective_at.get(key, self._objective)
        return CheckResult(feasible=True, objective=obj, violations=[], integrality_ok=True)
