"""Independent Z3 encoding of furniture-workshop-v1.

Built from the narrative, not from CVXPY or OR-Tools source. This is the
verification-layer IR: used to check candidate solutions, never to generate
solver code.
"""

from __future__ import annotations

from z3 import Int, Solver

from dubito.z3check import Z3Spec


class FurnitureZ3(Z3Spec):
    problem_id = "furniture-workshop-v1"
    variables = ("tables", "chairs")

    def encode(self) -> tuple[Solver, dict[str, object]]:
        tables = Int("tables")
        chairs = Int("chairs")
        solver = Solver()
        solver.add(tables >= 0)
        solver.add(chairs >= 0)
        solver.add(3 * tables + chairs <= 12)
        solver.add(2 * tables + chairs <= 10)
        solver.add(chairs >= 2 * tables)
        return solver, {"tables": tables, "chairs": chairs}


def spec() -> FurnitureZ3:
    return FurnitureZ3()
