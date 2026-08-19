"""Planted bug: labor resource constraint omitted."""

from __future__ import annotations

from ortools.linear_solver import pywraplp

from dubito.backends.ortools_backend import OrtoolsFormulation

_WOOD_PER = {"tables": 3, "chairs": 1}
_WOOD_STOCK = 12
_PROFIT = {"tables": 50, "chairs": 20}
_CHAIRS_PER_TABLE = 2


class FurnitureOrtoolsMissingLabor(OrtoolsFormulation):
    name = "ortools_missing_labor"
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
        # BUG: labor constraint never added
        solver.Add(chairs >= _CHAIRS_PER_TABLE * tables, "marketing_mix")
        objective = solver.Objective()
        objective.SetCoefficient(tables, _PROFIT["tables"])
        objective.SetCoefficient(chairs, _PROFIT["chairs"])
        objective.SetMaximization()
        return solver, {"tables": tables, "chairs": chairs}


def formulation() -> FurnitureOrtoolsMissingLabor:
    return FurnitureOrtoolsMissingLabor()
