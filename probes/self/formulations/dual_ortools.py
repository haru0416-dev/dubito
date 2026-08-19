"""OR-Tools GLOP encoding of furniture-dual-v1.

Covering coefficients are local. Not generated from the CVXPY file.
GLOP is an LP solver; this is not the CBC path used for the primal MILP.
"""

from __future__ import annotations

from ortools.linear_solver import pywraplp

from dubito.backends.ortools_backend import OrtoolsFormulation

_STOCK_COST = {"wood_price": 12.0, "labor_price": 10.0, "mix_price": 0.0}
_TABLE = {"wood_price": 3.0, "labor_price": 2.0, "mix_price": 2.0}
_CHAIR = {"wood_price": 1.0, "labor_price": 1.0, "mix_price": -1.0}
_TABLE_PROFIT = 50.0
_CHAIR_PROFIT = 20.0


class FurnitureDualOrtools(OrtoolsFormulation):
    name = "dual_ortools"
    problem_id = "furniture-dual-v1"
    variables = ("wood_price", "labor_price", "mix_price")
    sense = "min"
    solver_id = "GLOP"

    def _build(self) -> tuple[pywraplp.Solver, dict[str, pywraplp.Variable]]:
        solver = pywraplp.Solver.CreateSolver(self.solver_id)
        if solver is None:
            raise RuntimeError("GLOP solver unavailable")
        prices = {
            name: solver.NumVar(0.0, solver.infinity(), name)
            for name in self.variables
        }
        solver.Add(
            sum(_TABLE[name] * prices[name] for name in self.variables) >= _TABLE_PROFIT,
            "table_cover",
        )
        solver.Add(
            sum(_CHAIR[name] * prices[name] for name in self.variables) >= _CHAIR_PROFIT,
            "chair_cover",
        )
        objective = solver.Objective()
        for name, var in prices.items():
            objective.SetCoefficient(var, _STOCK_COST[name])
        objective.SetMinimization()
        return solver, prices


def formulation() -> FurnitureDualOrtools:
    return FurnitureDualOrtools()
