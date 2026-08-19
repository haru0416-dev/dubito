"""Planted bug: this encoding imports the verification IR loader.

The model is otherwise the furniture workshop. Exchange+SMT can still agree
with a clean peer; the code layer must disagree.
"""

from __future__ import annotations

import cvxpy as cp

from dubito.backends.cvxpy_backend import CvxpyFormulation
from dubito.problem import as_linear_ir  # the violation — do not copy this

_ = as_linear_ir


class FurnitureFromIr(CvxpyFormulation):
    name = "cvxpy_from_ir"
    problem_id = "furniture-workshop-v1"
    variables = ("tables", "chairs")
    sense = "max"

    def _problem(self) -> tuple[cp.Problem, dict[str, cp.Variable]]:
        tables = cp.Variable(integer=True, name="tables", nonneg=True)
        chairs = cp.Variable(integer=True, name="chairs", nonneg=True)
        profit = 50 * tables + 20 * chairs
        wood = 3 * tables + chairs <= 12
        labor = 2 * tables + chairs <= 10
        mix = chairs >= 2 * tables
        problem = cp.Problem(cp.Maximize(profit), [wood, labor, mix])
        return problem, {"tables": tables, "chairs": chairs}


def formulation() -> FurnitureFromIr:
    return FurnitureFromIr()
