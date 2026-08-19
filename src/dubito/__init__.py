"""dubito — cross-check solutions across independently formulated solvers.

Working name. The product name is deliberately unset until the Phase 0
hypothesis is confirmed and the Phase 1 shape is stable.
"""

from dubito.exchange import exchange_check
from dubito.load import load_formulation
from dubito.score import score_to_dict
from dubito.model import Formulation, ScoreVector, SolveResult, Tolerances

__version__ = "0.0.1"
__all__ = [
    "Formulation",
    "ScoreVector",
    "SolveResult",
    "Tolerances",
    "exchange_check",
    "load_formulation",
    "score_to_dict",
    "__version__",
]
