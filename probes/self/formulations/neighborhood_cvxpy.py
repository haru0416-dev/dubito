"""CVXPY integer encoding of furniture-local-opt-v1.

Incumbent ball is written as explicit inequalities. Resource rows are local.
"""

from __future__ import annotations

import cvxpy as cp

from dubito.backends.cvxpy_backend import CvxpyFormulation


class FurnitureNeighborhoodCvxpy(CvxpyFormulation):
    name = "neighborhood_cvxpy"
    problem_id = "furniture-local-opt-v1"
    variables = ("tables", "chairs")
    sense = "max"

    def _problem(self) -> tuple[cp.Problem, dict[str, cp.Variable]]:
        tables = cp.Variable(integer=True, name="tables")
        chairs = cp.Variable(integer=True, name="chairs")
        profit = 50 * tables + 20 * chairs
        # L-inf radius 2 around (2, 6)
        ball = [
            tables >= 0,
            tables <= 4,
            chairs >= 4,
            chairs <= 8,
        ]
        wood = 3 * tables + chairs <= 12
        labor = 2 * tables + chairs <= 10
        mix = chairs >= 2 * tables
        problem = cp.Problem(cp.Maximize(profit), [*ball, wood, labor, mix])
        return problem, {"tables": tables, "chairs": chairs}


def formulation() -> FurnitureNeighborhoodCvxpy:
    return FurnitureNeighborhoodCvxpy()
