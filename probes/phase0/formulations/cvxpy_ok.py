"""CVXPY encoding of furniture-workshop-v1, written in CVXPY idiom.

Constraints are local to this file. Do not import them from a shared IR.
"""

from __future__ import annotations

import cvxpy as cp

from dubito.backends.cvxpy_backend import CvxpyFormulation


class FurnitureCvxpy(CvxpyFormulation):
    name = "cvxpy_ok"
    problem_id = "furniture-workshop-v1"
    variables = ("tables", "chairs")
    sense = "max"

    def _problem(self) -> tuple[cp.Problem, dict[str, cp.Variable]]:
        tables = cp.Variable(integer=True, name="tables", nonneg=True)
        chairs = cp.Variable(integer=True, name="chairs", nonneg=True)
        profit = 50 * tables + 20 * chairs
        wood = 3 * tables + chairs <= 12
        labor = 2 * tables + chairs <= 10
        # marketing: at least two chairs per table
        mix = chairs >= 2 * tables
        problem = cp.Problem(cp.Maximize(profit), [wood, labor, mix])
        return problem, {"tables": tables, "chairs": chairs}


def formulation() -> FurnitureCvxpy:
    return FurnitureCvxpy()
