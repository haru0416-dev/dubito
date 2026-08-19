"""Planted bug: dual covering written as <= (as if the primal were a min).

Independent of dual_cvxpy.py. YAML verification still uses >=.
"""

from __future__ import annotations

import cvxpy as cp

from dubito.backends.cvxpy_backend import CvxpyFormulation


class FurnitureDualInvertedCover(CvxpyFormulation):
    name = "dual_inverted_cover"
    problem_id = "furniture-dual-v1"
    variables = ("wood_price", "labor_price", "mix_price")
    sense = "min"
    solver = cp.GLPK

    def _problem(self) -> tuple[cp.Problem, dict[str, cp.Variable]]:
        wood = cp.Variable(nonneg=True, name="wood_price")
        labor = cp.Variable(nonneg=True, name="labor_price")
        mix = cp.Variable(nonneg=True, name="mix_price")
        cost = 12 * wood + 10 * labor
        table_cover = 3 * wood + 2 * labor + 2 * mix <= 50
        chair_cover = wood + labor - mix <= 20
        problem = cp.Problem(cp.Minimize(cost), [table_cover, chair_cover])
        return problem, {
            "wood_price": wood,
            "labor_price": labor,
            "mix_price": mix,
        }


def formulation() -> FurnitureDualInvertedCover:
    return FurnitureDualInvertedCover()
