"""Planted bug: mix inverted inside the local-opt box (tables >= 2*chairs)."""

from __future__ import annotations

import cvxpy as cp

from dubito.backends.cvxpy_backend import CvxpyFormulation


class FurnitureNeighborhoodInvertedMix(CvxpyFormulation):
    name = "neighborhood_inverted_mix"
    problem_id = "furniture-local-opt-v1"
    variables = ("tables", "chairs")
    sense = "max"

    def _problem(self) -> tuple[cp.Problem, dict[str, cp.Variable]]:
        tables = cp.Variable(integer=True, name="tables")
        chairs = cp.Variable(integer=True, name="chairs")
        profit = 50 * tables + 20 * chairs
        ball = [tables >= 0, tables <= 4, chairs >= 4, chairs <= 8]
        wood = 3 * tables + chairs <= 12
        labor = 2 * tables + chairs <= 10
        mix = tables >= 2 * chairs
        problem = cp.Problem(cp.Maximize(profit), [*ball, wood, labor, mix])
        return problem, {"tables": tables, "chairs": chairs}


def formulation() -> FurnitureNeighborhoodInvertedMix:
    return FurnitureNeighborhoodInvertedMix()
