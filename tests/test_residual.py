from __future__ import annotations

import pytest

from dubito.model import Tolerances
from dubito.problem import ProblemSpecError, parse_problem
from dubito.residual import evaluate_residual


def _rosenbrock_raw() -> dict[str, object]:
    return {
        "id": "rosenbrock-v1",
        "class": "nlp",
        "sense": "min",
        "variables": {
            "x": {"kind": "continuous"},
            "y": {"kind": "continuous"},
        },
        "verification": {
            "kind": "residual",
            "objective": {"expr": "(1 - x)**2 + 100 * (y - x**2)**2"},
        },
    }


def test_residual_accepts_known_minimizer() -> None:
    problem = parse_problem(_rosenbrock_raw())
    check = evaluate_residual(problem, {"x": 1.0, "y": 1.0}, Tolerances())
    assert check.feasible
    assert check.objective == pytest.approx(0.0)


def test_residual_reports_objective_at_origin() -> None:
    problem = parse_problem(_rosenbrock_raw())
    check = evaluate_residual(problem, {"x": 0.0, "y": 0.0}, Tolerances())
    assert check.feasible
    assert check.objective == pytest.approx(1.0)


def test_nlp_rejects_linear_ir() -> None:
    with pytest.raises(ProblemSpecError, match="kind residual"):
        parse_problem(
            {
                "id": "bad",
                "class": "nlp",
                "sense": "min",
                "variables": {"x": {"kind": "continuous"}},
                "verification": {
                    "constraints": [{"name": "c", "terms": {"x": 1}, "op": ">=", "rhs": 0}],
                    "objective": {"terms": {"x": 1}},
                },
            }
        )


def test_milp_rejects_residual_ir() -> None:
    with pytest.raises(ProblemSpecError, match="kind linear"):
        parse_problem(
            {
                "id": "bad",
                "class": "milp",
                "sense": "min",
                "variables": {"x": {"kind": "integer", "lower": 0}},
                "verification": {"kind": "residual", "objective": {"expr": "x**2"}},
            }
        )


def test_residual_constraint_violation() -> None:
    problem = parse_problem(
        {
            "id": "disk",
            "class": "nlp",
            "sense": "min",
            "variables": {"x": {"kind": "continuous"}, "y": {"kind": "continuous"}},
            "verification": {
                "kind": "residual",
                "constraints": [
                    {"name": "disk", "expr": "x**2 + y**2", "op": "<=", "rhs": 1},
                ],
                "objective": {"expr": "x**2 + y**2"},
            },
        }
    )
    inside = evaluate_residual(problem, {"x": 0.3, "y": 0.4}, Tolerances())
    assert inside.feasible
    outside = evaluate_residual(problem, {"x": 1.0, "y": 1.0}, Tolerances())
    assert not outside.feasible
    assert any(item.name == "disk" for item in outside.violations)
