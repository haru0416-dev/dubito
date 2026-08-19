"""dubito — cross-check solutions across independently formulated solvers.

Working name. The product name is deliberately unset until the Phase 0
hypothesis is confirmed and the Phase 1 shape is stable.
"""

from dubito.agent import agent_brief, playbook, spec_for_agent
from dubito.cegis import run_cegis
from dubito.exchange import exchange_check
from dubito.faces import call_tool, evaluate_tool, tool_descriptors
from dubito.lessons import distill as distill_lessons
from dubito.load import load_formulation
from dubito.pipeline import verify
from dubito.problem import load_problem
from dubito.router import route
from dubito.score import score_to_dict
from dubito.model import Formulation, ScoreVector, SolveResult, Tolerances

__version__ = "0.4.0"
__all__ = [
    "Formulation",
    "ScoreVector",
    "SolveResult",
    "Tolerances",
    "agent_brief",
    "call_tool",
    "distill_lessons",
    "evaluate_tool",
    "exchange_check",
    "load_formulation",
    "load_problem",
    "playbook",
    "route",
    "run_cegis",
    "score_to_dict",
    "spec_for_agent",
    "tool_descriptors",
    "verify",
    "__version__",
]
