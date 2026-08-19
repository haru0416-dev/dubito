from __future__ import annotations

from pathlib import Path

import pytest

from dubito.load import load_formulation
from dubito.model import SolveResult
from dubito.pipeline import verify
from dubito.problem import load_problem
from dubito.properties import check_properties

_PHASE3 = Path(__file__).resolve().parents[1] / "probes/phase3"
_PROBLEM = _PHASE3 / "rosenbrock.yaml"
_NELDER = _PHASE3 / "formulations/scipy_nelder_mead.py"
_LBFGSB = _PHASE3 / "formulations/scipy_lbfgsb.py"
_BUG = _PHASE3 / "bugs/wrong_valley.py"


def test_rosenbrock_pair_agrees_on_residual() -> None:
    score = verify(
        [load_formulation(_NELDER), load_formulation(_LBFGSB)],
        load_problem(_PROBLEM),
    )
    assert score.verdict == "agree"
    assert score.verification_strength == "exchange+residual+properties"
    assert score.layers["exchange"] == "ran"
    assert score.layers["residual"] == "ran"
    assert score.layers["properties"] == "ran"
    assert "smt" not in score.layers
    assert "dual" not in score.layers
    assert score.dual_bound is None
    assert all(score.residual_feasible.values())
    assert all(score.residual_objective_match.values())
    assert score.properties_ok.get("local_optimality") is True
    assert "global certificate" in score.guarantee or "local" in score.guarantee.lower()
    for value in score.objective.values():
        assert value == pytest.approx(0.0, abs=1e-4)


def test_wrong_valley_disagrees_with_peer_and_residual() -> None:
    score = verify(
        [load_formulation(_NELDER), load_formulation(_BUG)],
        load_problem(_PROBLEM),
    )
    assert score.verdict == "disagree"
    kinds = {item["kind"] for item in score.counterexamples}
    assert "objective_mismatch" in kinds or "residual_objective_mismatch" in kinds or "claimed_optima_mismatch" in kinds


def test_continuous_local_optimality_flags_origin() -> None:
    problem = load_problem(_PROBLEM)
    origin = SolveResult(
        solver="origin",
        status="optimal",
        assignment={"x": 0.0, "y": 0.0},
        objective=1.0,
        runtime_ms=0.0,
    )
    report = check_properties(
        problem,
        solves={"origin": origin},
        witness_feasible={"origin": True},
    )
    assert report.ok["local_optimality"] is False
    assert any(item["kind"] == "local_optimality" for item in report.counterexamples)
