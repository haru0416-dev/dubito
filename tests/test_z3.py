from __future__ import annotations

import importlib.util
from pathlib import Path

from dubito.load import load_formulation
from dubito.model import Tolerances

_PHASE0 = Path(__file__).resolve().parents[1] / "probes/phase0"


def _load_z3():
    path = _PHASE0 / "z3_spec.py"
    spec = importlib.util.spec_from_file_location("furniture_z3_spec", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.spec()


def test_z3_accepts_known_optimum_and_rejects_infeasible() -> None:
    z3 = _load_z3()
    tol = Tolerances()
    ok = z3.check_assignment({"tables": 2.0, "chairs": 6.0}, tol)
    assert ok.feasible
    labor_violation = z3.check_assignment({"tables": 0.0, "chairs": 12.0}, tol)
    assert labor_violation.feasible is False
    mix_violation = z3.check_assignment({"tables": 4.0, "chairs": 0.0}, tol)
    assert mix_violation.feasible is False


def test_z3_agrees_with_independent_solvers() -> None:
    z3 = _load_z3()
    tol = Tolerances()
    for path in (
        _PHASE0 / "formulations/cvxpy_ok.py",
        _PHASE0 / "formulations/ortools_ok.py",
    ):
        solved = load_formulation(path).solve()
        checked = z3.check_assignment(solved.assignment, tol)
        assert checked.feasible, path
