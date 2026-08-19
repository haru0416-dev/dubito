from __future__ import annotations

from pathlib import Path

from dubito.load import load_formulation
from dubito.pipeline import verify
from dubito.problem import load_problem

_PHASE0 = Path(__file__).resolve().parents[1] / "probes/phase0"
_PROBLEM = _PHASE0 / "furniture.yaml"
_OK_CVXPY = _PHASE0 / "formulations/cvxpy_ok.py"
_OK_ORTOOLS = _PHASE0 / "formulations/ortools_ok.py"


def test_ok_pair_agrees_with_smt() -> None:
    score = verify(
        [load_formulation(_OK_CVXPY), load_formulation(_OK_ORTOOLS)],
        load_problem(_PROBLEM),
    )
    assert score.verdict == "agree"
    assert score.verification_strength == "exchange+smt"
    assert score.smt_feasible == {"cvxpy_ok": True, "ortools_ok": True}
    assert all(score.smt_objective_match.values())


def test_inverted_fails_smt_and_exchange() -> None:
    score = verify(
        [
            load_formulation(_OK_CVXPY),
            load_formulation(_PHASE0 / "bugs/cvxpy_inverted_ratio.py"),
        ],
        load_problem(_PROBLEM),
    )
    assert score.verdict == "disagree"
    assert score.smt_feasible["cvxpy_ok"] is True
    assert score.smt_feasible["cvxpy_inverted_ratio"] is False
    kinds = {item["kind"] for item in score.counterexamples}
    assert "smt_infeasible" in kinds


def test_correlated_inverted_ratio_is_caught_by_smt() -> None:
    """Same bug in both backends: exchange agrees, verification IR does not."""

    score = verify(
        [
            load_formulation(_PHASE0 / "bugs/cvxpy_inverted_ratio.py"),
            load_formulation(_PHASE0 / "bugs/ortools_inverted_ratio.py"),
        ],
        load_problem(_PROBLEM),
    )
    assert score.agreement == 1.0
    assert score.claimed_optima_match is True
    assert score.verdict == "disagree"
    assert "solvers agree with each other but not with the verification IR" in score.notes
    assert not any(score.smt_feasible.values())


def test_wrong_profit_fails_smt_objective() -> None:
    score = verify(
        [
            load_formulation(_OK_ORTOOLS),
            load_formulation(_PHASE0 / "bugs/cvxpy_wrong_profit.py"),
        ],
        load_problem(_PROBLEM),
    )
    assert score.verdict == "disagree"
    assert score.smt_feasible["ortools_ok"] is True
    assert score.smt_objective_match["ortools_ok"] is True
    kinds = {item["kind"] for item in score.counterexamples}
    assert "smt_objective_mismatch" in kinds or "objective_mismatch" in kinds
