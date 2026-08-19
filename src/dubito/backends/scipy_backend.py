"""SciPy runtime adapter. Subclasses independently write `_objective()`."""

from __future__ import annotations

import time
from abc import abstractmethod
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import minimize

from dubito.model import (
    CheckResult,
    ConstraintViolation,
    Formulation,
    Sense,
    SolveResult,
    Tolerances,
)
from dubito.numeric import as_number, bound_violation


class ScipyFormulation(Formulation):
    """Nelder-Mead / L-BFGS-B helper. Not a compilation of the residual IR."""

    sense: Sense = "min"
    method: str = "L-BFGS-B"
    seed: int = 0

    @abstractmethod
    def _objective(self, vec: np.ndarray) -> float:
        raise NotImplementedError

    def _x0(self) -> np.ndarray:
        return np.zeros(len(self.variables))

    def _bounds(self) -> Sequence[tuple[float | None, float | None]] | None:
        return None

    def _minimize_options(self) -> dict[str, object]:
        return {}

    def solve(self) -> SolveResult:
        started = time.perf_counter()
        try:
            options = self._minimize_options()
            result = minimize(
                self._objective,
                np.asarray(self._x0(), dtype=float),
                method=self.method,
                bounds=self._bounds(),
                options=options or None,
            )
        except Exception as exc:  # noqa: BLE001
            return SolveResult(
                solver=self.name,
                status="error",
                assignment={},
                objective=None,
                runtime_ms=(time.perf_counter() - started) * 1000,
                error=str(exc),
            )
        assignment = {
            name: float(result.x[index]) for index, name in enumerate(self.variables)
        }
        status = "optimal" if bool(result.success) else "feasible"
        if not result.success and not np.isfinite(result.fun):
            status = "error"
        return SolveResult(
            solver=self.name,
            status=status,  # type: ignore[arg-type]
            assignment=assignment,
            objective=float(result.fun),
            runtime_ms=(time.perf_counter() - started) * 1000,
            error=None if result.success else str(result.message),
        )

    def check(self, assignment: Mapping[str, float], tol: Tolerances) -> CheckResult:
        vec = np.array([as_number(assignment[name]) for name in self.variables], dtype=float)
        violations: list[ConstraintViolation] = []
        bounds = self._bounds()
        if bounds is not None:
            for index, name in enumerate(self.variables):
                lower, upper = bounds[index]
                viol = bound_violation(float(vec[index]), lower, upper)
                if viol > tol.primal_feasibility:
                    violations.append(
                        ConstraintViolation(
                            name=f"bound:{name}",
                            violation=viol,
                            detail=f"{name}={vec[index]} outside [{lower}, {upper}]",
                        )
                    )
        objective = float(self._objective(vec))
        return CheckResult(
            feasible=not violations,
            objective=objective,
            violations=violations,
            integrality_ok=True,
        )
