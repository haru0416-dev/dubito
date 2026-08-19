"""Planted bug: table profit is 40 instead of 50 (OR-Tools)."""

from __future__ import annotations

from ortools.linear_solver import pywraplp

from dubito.backends.ortools_backend import OrtoolsFormulation

_WOOD_PER = {"tables": 3, "chairs": 1}
_WOOD_STOCK = 12
_LABOR_PER = {"tables": 2, "chairs": 1}
_LABOR_STOCK = 10
_CHAIRS_PER_TABLE = 2


class FurnitureOrtoolsWrongProfit(OrtoolsFormulation):
    name = "ortools_wrong_profit"
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
        solver.Add(chairs >= _CHAIRS_PER_TABLE * tables, "marketing_mix")
        objective = solver.Objective()
        # BUG: 40 instead of 50
        objective.SetCoefficient(tables, 40)
        objective.SetCoefficient(chairs, 20)
        objective.SetMaximization()
        return solver, {"tables": tables, "chairs": chairs}


def formulation() -> FurnitureOrtoolsWrongProfit:
    return FurnitureOrtoolsWrongProfit()
