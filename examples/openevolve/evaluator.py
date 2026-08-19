"""OpenEvolve adapter example.

OpenEvolve calls `evaluate(program_path)` and expects a dict of floats.
Point this file at an independently written formulation module.

    python -c "from examples.openevolve.evaluator import evaluate; \
print(evaluate('probes/phase0/formulations/cvxpy_ok.py'))"
"""

from dubito.evaluator import evaluate

__all__ = ["evaluate"]
