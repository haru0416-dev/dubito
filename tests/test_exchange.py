from __future__ import annotations

from dubito.exchange import exchange_check
from dubito.numeric import nearest_int, numbers_close
from dubito.model import Tolerances
from tests.fakes import FakeFormulation


def test_numbers_close_uses_relative_scale() -> None:
    tol = Tolerances(objective_abs=1e-6, objective_rel=1e-6)
    assert numbers_close(220.0, 220.0 + 1e-8, tol)
    assert not numbers_close(220.0, 200.0, tol)


def test_nearest_int_respects_integrality_tol() -> None:
    tol = Tolerances(integrality=1e-8)
    assert nearest_int(2.0 + 1e-12, tol) == 2
    assert nearest_int(2.4, tol) is None


def test_agreeing_fakes_return_agree() -> None:
    a = FakeFormulation("a", {"x": 1.0}, 10.0)
    b = FakeFormulation("b", {"x": 1.0}, 10.0)
    score = exchange_check([a, b])
    assert score.verdict == "agree"
    assert score.agreement == 1.0
    assert score.claimed_optima_match is True
    assert score.counterexamples == []


def test_infeasible_exchange_is_disagree() -> None:
    a = FakeFormulation("a", {"x": 1.0}, 10.0)
    b = FakeFormulation(
        "b",
        {"x": 2.0},
        4.0,
        rejected={(1.0,): "x bound"},
        objective_at={(1.0,): 10.0, (2.0,): 4.0},
    )
    score = exchange_check([a, b])
    assert score.verdict == "disagree"
    assert score.agreement < 1.0
    kinds = {item["kind"] for item in score.counterexamples}
    assert "infeasible" in kinds


def test_objective_mismatch_is_disagree() -> None:
    a = FakeFormulation("a", {"x": 1.0}, 10.0, objective_at={(1.0,): 10.0})
    b = FakeFormulation("b", {"x": 1.0}, 7.0, objective_at={(1.0,): 7.0})
    score = exchange_check([a, b])
    assert score.verdict == "disagree"
    kinds = {item["kind"] for item in score.counterexamples}
    assert "objective_mismatch" in kinds or "claimed_optima_mismatch" in kinds


def test_solver_error_is_error_verdict() -> None:
    a = FakeFormulation("a", {"x": 1.0}, 10.0)
    b = FakeFormulation("b", {"x": 1.0}, 10.0, error="boom")
    score = exchange_check([a, b])
    assert score.verdict == "error"


def test_score_vector_has_required_keys() -> None:
    a = FakeFormulation("a", {"x": 1.0}, 10.0)
    b = FakeFormulation("b", {"x": 1.0}, 10.0)
    payload = exchange_check([a, b]).to_dict()
    for key in (
        "problem_id",
        "verdict",
        "verification_strength",
        "guarantee",
        "feasible",
        "agreement",
        "objective",
        "optimality_status",
        "counterexamples",
        "runtime_ms",
        "tolerances",
        "smt_feasible",
        "smt_objective_match",
        "dual_bound",
        "dual_gap",
        "dual_closed",
        "properties_ok",
        "code_ok",
        "layers",
    ):
        assert key in payload
    assert payload["verification_strength"] == "exchange"
    assert payload["smt_feasible"] == {}
