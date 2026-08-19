"""Nelder-Mead encoding of rosenbrock-v1, written in SciPy idiom.

The objective is local to this file. Do not import it from the YAML residual IR.
"""

from __future__ import annotations

import numpy as np

from dubito.backends.scipy_backend import ScipyFormulation


class RosenbrockNelderMead(ScipyFormulation):
    name = "rosenbrock_nelder_mead"
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
        return (1.0 - x) ** 2 + 100.0 * (y - x * x) ** 2


def formulation() -> RosenbrockNelderMead:
    return RosenbrockNelderMead()
