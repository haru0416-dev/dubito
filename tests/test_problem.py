from __future__ import annotations

from pathlib import Path

import pytest

from dubito.ir import evaluate_ir
from dubito.problem import ProblemSpecError, load_problem
from dubito.model import Tolerances
from dubito.z3check import LinearZ3Spec

_YAML = Path(__file__).resolve().parents[1] / "probes/phase0/furniture.yaml"


def test_load_furniture_problem() -> None:
    problem = load_problem(_YAML)
    assert problem.id == "furniture-workshop-v1"
    assert problem.problem_class == "milp"
    assert problem.sense == "max"
    assert tuple(problem.variables) == ("tables", "chairs")
    assert problem.verification is not None
    assert len(problem.verification.constraints) == 3


def test_rejects_unknown_class() -> None:
    from dubito.problem import parse_problem

    with pytest.raises(ProblemSpecError, match="not a Phase 1 class"):
        parse_problem(
            {
                "id": "x",
                "class": "convex",
                "sense": "min",
                "variables": {"x": {"kind": "continuous"}},
            }
        )


def test_rejects_unknown_variable_in_ir() -> None:
    from dubito.problem import parse_problem

    with pytest.raises(ProblemSpecError, match="unknown variable"):
        parse_problem(
            {
                "id": "x",
                "class": "milp",
                "sense": "max",
                "variables": {"tables": {"kind": "integer", "lower": 0}},
                "verification": {
                    "constraints": [
                        {"name": "c", "terms": {"chairs": 1}, "op": "<=", "rhs": 1},
                    ],
                    "objective": {"terms": {"tables": 1}},
                },
            }
        )


def test_ir_accepts_known_optimum() -> None:
    problem = load_problem(_YAML)
    check = evaluate_ir(problem, {"tables": 2.0, "chairs": 6.0}, Tolerances())
    assert check.feasible
    assert check.objective == 220.0


def test_ir_rejects_labor_and_mix_violations() -> None:
    problem = load_problem(_YAML)
    labor = evaluate_ir(problem, {"tables": 0.0, "chairs": 12.0}, Tolerances())
    assert not labor.feasible
    assert any(item.name == "labor" for item in labor.violations)
    mix = evaluate_ir(problem, {"tables": 4.0, "chairs": 0.0}, Tolerances())
    assert not mix.feasible
    assert any(item.name == "mix" for item in mix.violations)


def test_z3_ir_matches_handwritten_spec() -> None:
    import importlib.util

    problem = load_problem(_YAML)
    z3_ir = LinearZ3Spec(problem)
    path = _YAML.parent / "z3_spec.py"
    spec = importlib.util.spec_from_file_location("furniture_z3_spec", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handwritten = module.spec()
    tol = Tolerances()
    points = [
        {"tables": 2.0, "chairs": 6.0},
        {"tables": 0.0, "chairs": 12.0},
        {"tables": 4.0, "chairs": 0.0},
        {"tables": 0.0, "chairs": 10.0},
    ]
    for point in points:
        assert z3_ir.check_assignment(point, tol).feasible == handwritten.check_assignment(point, tol).feasible
