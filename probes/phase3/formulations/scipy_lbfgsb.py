"""L-BFGS-B encoding of rosenbrock-v1, written independently of Nelder-Mead.

Do not import the YAML residual block or the peer formulation's objective.
"""

from __future__ import annotations

import numpy as np

from dubito.backends.scipy_backend import ScipyFormulation


class RosenbrockLbfgsb(ScipyFormulation):
    name = "rosenbrock_lbfgsb"
    problem_id = "rosenbrock-v1"
    variables = ("x", "y")
    sense = "min"
    method = "L-BFGS-B"

    def _x0(self) -> np.ndarray:
        return np.array([-1.2, 1.0], dtype=float)

    def _minimize_options(self) -> dict[str, object]:
        return {"gtol": 1e-10, "maxiter": 500}

    def _objective(self, vec: np.ndarray) -> float:
        xx = float(vec[0])
        yy = float(vec[1])
        valley = yy - xx * xx
        return (1.0 - xx) ** 2 + 100.0 * valley * valley


def formulation() -> RosenbrockLbfgsb:
    return RosenbrockLbfgsb()
