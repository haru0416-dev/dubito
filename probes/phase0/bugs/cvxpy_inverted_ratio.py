"""Planted bug: marketing mix inverted.

Correct: at least two chairs per table (chairs >= 2 * tables).
Buggy:   at least two tables per chair  (tables >= 2 * chairs).
"""

from __future__ import annotations

import cvxpy as cp

from dubito.backends.cvxpy_backend import CvxpyFormulation


class FurnitureCvxpyInvertedRatio(CvxpyFormulation):
    name = "cvxpy_inverted_ratio"
    problem_id = "furniture-workshop-v1"
    variables = ("tables", "chairs")
    sense = "max"

    def _problem(self) -> tuple[cp.Problem, dict[str, cp.Variable]]:
        tables = cp.Variable(integer=True, name="tables", nonneg=True)
        chairs = cp.Variable(integer=True, name="chairs", nonneg=True)
        profit = 50 * tables + 20 * chairs
        wood = 3 * tables + chairs <= 12
        labor = 2 * tables + chairs <= 10
        # BUG: inverted mix constraint
        mix = tables >= 2 * chairs
        problem = cp.Problem(cp.Maximize(profit), [wood, labor, mix])
        return problem, {"tables": tables, "chairs": chairs}


def formulation() -> FurnitureCvxpyInvertedRatio:
    return FurnitureCvxpyInvertedRatio()
