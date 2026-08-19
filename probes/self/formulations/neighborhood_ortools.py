"""OR-Tools CBC encoding of furniture-local-opt-v1.

The search box is on the variable bounds, not extra constraints.
Constants are not shared with the CVXPY neighborhood file.
"""

from __future__ import annotations

from ortools.linear_solver import pywraplp

from dubito.backends.ortools_backend import OrtoolsFormulation

_INCUMBENT = {"tables": 2, "chairs": 6}
_RADIUS = 2
_WOOD = (3, 1, 12)
_LABOR = (2, 1, 10)
_PROFIT = (50, 20)
_CHAIRS_PER_TABLE = 2


class FurnitureNeighborhoodOrtools(OrtoolsFormulation):
    name = "neighborhood_ortools"
    problem_id = "furniture-local-opt-v1"
    variables = ("tables", "chairs")
    sense = "max"

    def _build(self) -> tuple[pywraplp.Solver, dict[str, pywraplp.Variable]]:
        solver = pywraplp.Solver.CreateSolver(self.solver_id)
        if solver is None:
            raise RuntimeError("CBC solver unavailable")
        tables = solver.IntVar(
            _INCUMBENT["tables"] - _RADIUS,
            _INCUMBENT["tables"] + _RADIUS,
            "tables",
        )
        chairs = solver.IntVar(
            _INCUMBENT["chairs"] - _RADIUS,
            _INCUMBENT["chairs"] + _RADIUS,
            "chairs",
        )
        tw, cw, wood_stock = _WOOD
        tl, cl, labor_stock = _LABOR
        solver.Add(tw * tables + cw * chairs <= wood_stock, "wood")
        solver.Add(tl * tables + cl * chairs <= labor_stock, "labor")
        solver.Add(chairs >= _CHAIRS_PER_TABLE * tables, "marketing_mix")
        objective = solver.Objective()
        objective.SetCoefficient(tables, _PROFIT[0])
        objective.SetCoefficient(chairs, _PROFIT[1])
        objective.SetMaximization()
        return solver, {"tables": tables, "chairs": chairs}


def formulation() -> FurnitureNeighborhoodOrtools:
    return FurnitureNeighborhoodOrtools()
