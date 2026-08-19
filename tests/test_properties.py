from __future__ import annotations

from pathlib import Path

from dubito.model import SolveResult
from dubito.problem import load_problem
from dubito.properties import check_properties

_YAML = Path(__file__).resolve().parents[1] / "probes/phase0/furniture.yaml"


def _solve(name: str, tables: float, chairs: float, objective: float) -> SolveResult:
    return SolveResult(
        solver=name,
        status="optimal",
        assignment={"tables": tables, "chairs": chairs},
        objective=objective,
        runtime_ms=0.0,
    )


def test_local_optimality_accepts_known_optimum() -> None:
    problem = load_problem(_YAML)
    report = check_properties(
        problem,
        solves={"ok": _solve("ok", 2.0, 6.0, 220.0)},
        smt_feasible={"ok": True},
    )
    assert report.ok["local_optimality"] is True
    assert report.ok["resource_monotonicity"] is True
    assert report.counterexamples == []


def test_local_optimality_flags_suboptimal_feasible_point() -> None:
    problem = load_problem(_YAML)
    report = check_properties(
        problem,
        solves={"sub": _solve("sub", 0.0, 10.0, 200.0)},
        smt_feasible={"sub": True},
    )
    assert report.ok["local_optimality"] is False
    kinds = {item["kind"] for item in report.counterexamples}
    assert "local_optimality" in kinds
    neighbor = next(item for item in report.counterexamples if item["kind"] == "local_optimality")
    assert neighbor["neighbor_objective"] > 200.0


def test_local_optimality_skips_smt_infeasible() -> None:
    problem = load_problem(_YAML)
    report = check_properties(
        problem,
        solves={"bad": _solve("bad", 4.0, 0.0, 200.0)},
        smt_feasible={"bad": False},
    )
    assert report.ok["local_optimality"] is None
    assert any("no SMT-feasible candidate" in note for note in report.notes)


def test_resource_monotonicity_uses_hypothesis_on_ir() -> None:
    problem = load_problem(_YAML)
    report = check_properties(problem, solves={}, smt_feasible={})
    assert report.ok["resource_monotonicity"] is True


def test_resource_monotonicity_flags_when_relaxation_worsens(monkeypatch) -> None:
    from dubito import properties as props

    problem = load_problem(_YAML)
    real = props.lp_relaxation_objective
    original_rhs = {item.name: item.rhs for item in problem.verification.constraints}

    def fake(current):
        opt = real(current)
        if opt is None:
            return None
        now = {item.name: item.rhs for item in current.verification.constraints}
        if now == original_rhs:
            return opt
        return opt - 50.0

    monkeypatch.setattr(props, "lp_relaxation_objective", fake)
    report = check_properties(problem, solves={}, smt_feasible={})
    assert report.ok["resource_monotonicity"] is False
    assert any(item["kind"] == "resource_monotonicity" for item in report.counterexamples)
