"""Planted NLP bug: shifted Rosenbrock valley.

(2 - x)^2 + 100 (y - x^2)^2 has minimizer (2, 4), not (1, 1).
A coefficient-10-vs-100 bug would share the same minimizer and is useless here.
"""

from __future__ import annotations

import numpy as np

from dubito.backends.scipy_backend import ScipyFormulation


class RosenbrockWrongValley(ScipyFormulation):
    name = "rosenbrock_wrong_valley"
    problem_id = "rosenbrock-v1"
    variables = ("x", "y")
    sense = "min"
    method = "Nelder-Mead"

    def _x0(self) -> np.ndarray:
        return np.array([-1.2, 1.0], dtype=float)

    def _minimize_options(self) -> dict[str, object]:
        return {"xatol": 1e-8, "fatol": 1e-12, "maxiter": 2000}

    def _objective(self, vec: np.ndarray) -> float:
        x = float(vec[0])
        y = float(vec[1])
        return (2.0 - x) ** 2 + 100.0 * (y - x * x) ** 2


def formulation() -> RosenbrockWrongValley:
    return RosenbrockWrongValley()
