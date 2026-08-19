"""Planted bug: marketing mix inverted (OR-Tools)."""

from __future__ import annotations

from ortools.linear_solver import pywraplp

from dubito.backends.ortools_backend import OrtoolsFormulation

_WOOD_PER = {"tables": 3, "chairs": 1}
_WOOD_STOCK = 12
_LABOR_PER = {"tables": 2, "chairs": 1}
_LABOR_STOCK = 10


class FurnitureOrtoolsInvertedRatio(OrtoolsFormulation):
    name = "ortools_inverted_ratio"
    problem_id = "furniture-workshop-v1"
    variables = ("tables", "chairs")
    sense = "max"

    def _build(self) -> tuple[pywraplp.Solver, dict[str, pywraplp.Variable]]:
        solver = pywraplp.Solver.CreateSolver(self.solver_id)
        if solver is None:
            raise RuntimeError("CBC solver unavailable")
        tables = solver.IntVar(0, solver.infinity(), "tables")
        chairs = solver.IntVar(0, solver.infinity(), "chairs")
        solver.Add(
            _WOOD_PER["tables"] * tables + _WOOD_PER["chairs"] * chairs <= _WOOD_STOCK,
            "wood",
        )
        solver.Add(
            _LABOR_PER["tables"] * tables + _LABOR_PER["chairs"] * chairs <= _LABOR_STOCK,
            "labor",
        )
        # BUG: inverted mix constraint
        solver.Add(tables >= 2 * chairs, "marketing_mix")
        objective = solver.Objective()
        objective.SetCoefficient(tables, 50)
        objective.SetCoefficient(chairs, 20)
        objective.SetMaximization()
        return solver, {"tables": tables, "chairs": chairs}


def formulation() -> FurnitureOrtoolsInvertedRatio:
    return FurnitureOrtoolsInvertedRatio()
