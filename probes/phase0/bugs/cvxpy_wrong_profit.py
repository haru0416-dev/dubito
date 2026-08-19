"""Planted bug: table profit is 40 instead of 50."""

from __future__ import annotations

import cvxpy as cp

from dubito.backends.cvxpy_backend import CvxpyFormulation


class FurnitureCvxpyWrongProfit(CvxpyFormulation):
    name = "cvxpy_wrong_profit"
    problem_id = "furniture-workshop-v1"
    variables = ("tables", "chairs")
    sense = "max"

    def _problem(self) -> tuple[cp.Problem, dict[str, cp.Variable]]:
        tables = cp.Variable(integer=True, name="tables", nonneg=True)
        chairs = cp.Variable(integer=True, name="chairs", nonneg=True)
        # BUG: 40 instead of 50
        profit = 40 * tables + 20 * chairs
        wood = 3 * tables + chairs <= 12
        labor = 2 * tables + chairs <= 10
        mix = chairs >= 2 * tables
        problem = cp.Problem(cp.Maximize(profit), [wood, labor, mix])
        return problem, {"tables": tables, "chairs": chairs}


def formulation() -> FurnitureCvxpyWrongProfit:
    return FurnitureCvxpyWrongProfit()
