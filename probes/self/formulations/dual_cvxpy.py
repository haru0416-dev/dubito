"""CVXPY/GLPK encoding of furniture-dual-v1.

Shadow-price algebra lives only in this file. Do not import the YAML IR
or the SciPy dual bound solver.
"""

from __future__ import annotations

import cvxpy as cp

from dubito.backends.cvxpy_backend import CvxpyFormulation


class FurnitureDualCvxpy(CvxpyFormulation):
    name = "dual_cvxpy"
    problem_id = "furniture-dual-v1"
    variables = ("wood_price", "labor_price", "mix_price")
    sense = "min"
    solver = cp.GLPK

    def _problem(self) -> tuple[cp.Problem, dict[str, cp.Variable]]:
        wood = cp.Variable(nonneg=True, name="wood_price")
        labor = cp.Variable(nonneg=True, name="labor_price")
        mix = cp.Variable(nonneg=True, name="mix_price")
        # Imputed cost of the stocks. Mix has zero right-hand side.
        cost = 12 * wood + 10 * labor
        table_cover = 3 * wood + 2 * labor + 2 * mix >= 50
        chair_cover = wood + labor - mix >= 20
        problem = cp.Problem(cp.Minimize(cost), [table_cover, chair_cover])
        return problem, {
            "wood_price": wood,
            "labor_price": labor,
            "mix_price": mix,
        }


def formulation() -> FurnitureDualCvxpy:
    return FurnitureDualCvxpy()
