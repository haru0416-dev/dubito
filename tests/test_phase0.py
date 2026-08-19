from __future__ import annotations

from pathlib import Path

from dubito.cli import run_phase0_probe
from dubito.evaluator import evaluate
from dubito.exchange import exchange_check
from dubito.load import load_formulation
from dubito.model import Tolerances

_PHASE0 = Path(__file__).resolve().parents[1] / "probes/phase0"
_OK_CVXPY = _PHASE0 / "formulations/cvxpy_ok.py"
_OK_ORTOOLS = _PHASE0 / "formulations/ortools_ok.py"


def test_independent_ok_formulations_agree() -> None:
    score = exchange_check(
        [load_formulation(_OK_CVXPY), load_formulation(_OK_ORTOOLS)],
        problem_id="furniture-workshop-v1",
    )
    assert score.verdict == "agree"
    assert score.agreement == 1.0
    assert score.claimed_optima_match is True
    for assignment in (
        load_formulation(_OK_CVXPY).solve().assignment,
        load_formulation(_OK_ORTOOLS).solve().assignment,
    ):
        assert round(assignment["tables"]) == 2
        assert round(assignment["chairs"]) == 6


def test_float_noise_does_not_false_disagree() -> None:
    cvxpy = load_formulation(_OK_CVXPY)
    ortools = load_formulation(_OK_ORTOOLS)
    solved = cvxpy.solve()
    noisy = {name: value + 1e-12 for name, value in solved.assignment.items()}
    check = ortools.check(noisy, Tolerances())
    assert check.feasible
    assert check.integrality_ok


def test_phase0_probe_hypothesis_holds() -> None:
    payload = run_phase0_probe()
    assert payload["hypothesis_holds"] is True
    assert payload["false_disagreement"] == 0
    assert payload["false_agreement"] == 0
    assert payload["detections"] == payload["bug_cases"]


def test_ok_formulations_do_not_share_an_ir() -> None:
    cvxpy_src = _OK_CVXPY.read_text()
    ortools_src = _OK_ORTOOLS.read_text()
    assert "ortools" not in cvxpy_src
    assert "cvxpy" not in ortools_src
    assert "furniture.yaml" not in cvxpy_src
    assert "furniture.yaml" not in ortools_src


def test_evaluator_returns_numeric_metrics(monkeypatch) -> None:
    monkeypatch.setenv("DUBITO_PEER_FORMULATIONS", str(_OK_ORTOOLS))
    metrics = evaluate(str(_OK_CVXPY))
    assert set(metrics) >= {"combined_score", "agreement", "all_feasible", "optima_match", "smt_ok"}
    assert metrics["combined_score"] == 1.0
    assert metrics["smt_ok"] == 1.0
    monkeypatch.setenv("DUBITO_PEER_FORMULATIONS", str(_OK_CVXPY))
    buggy = evaluate(str(_PHASE0 / "bugs/cvxpy_inverted_ratio.py"))
    assert buggy["combined_score"] == 0.0
