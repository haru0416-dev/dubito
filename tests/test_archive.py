from __future__ import annotations

from pathlib import Path

from dubito.archive import (
    ARCHIVE_SCHEMA,
    append_counterexamples,
    make_records,
    narrative_hash,
    read_archive,
    verification_hash,
)
from dubito.model import ScoreVector, Tolerances
from dubito.problem import load_problem

_YAML = Path(__file__).resolve().parents[1] / "probes/phase0/furniture.yaml"


def _score(*kinds: str) -> ScoreVector:
    counterexamples = [
        {"kind": kind, "assignment": {"tables": 4.0, "chairs": 0.0}, "solver": "buggy"}
        for kind in kinds
    ]
    return ScoreVector(
        problem_id="furniture-workshop-v1",
        verdict="disagree",
        verification_strength="exchange+smt",
        guarantee="test",
        feasible={"buggy": True},
        agreement=0.0,
        objective={"buggy": 200.0},
        optimality_status={"buggy": "optimal"},
        claimed_optima_match=None,
        counterexamples=list(counterexamples),
        runtime_ms={"buggy": 0.0},
        tolerances=Tolerances(),
    )


def test_archive_appends_one_record_per_counterexample(tmp_path: Path) -> None:
    problem = load_problem(_YAML)
    path = tmp_path / "cx.jsonl"
    n = append_counterexamples(
        path,
        _score("smt_infeasible", "dual_bound_exceeded"),
        problem,
        ["cvxpy_ok", "buggy"],
        timestamp="2026-08-19T00:00:00+00:00",
    )
    assert n == 2
    records = read_archive(path)
    assert len(records) == 2
    assert {item["kind"] for item in records} == {"smt_infeasible", "dual_bound_exceeded"}
    for item in records:
        assert item["schema"] == ARCHIVE_SCHEMA
        assert item["problem_id"] == "furniture-workshop-v1"
        assert item["formulation_names"] == ["cvxpy_ok", "buggy"]
        assert item["verdict"] == "disagree"
        assert item["narrative_hash"] == narrative_hash(problem.narrative)
        assert item["verification_hash"] == verification_hash(problem.verification)
        assert item["timestamp"] == "2026-08-19T00:00:00+00:00"
        assert item["assignment"] == {"tables": 4.0, "chairs": 0.0}


def test_hashes_are_stable_and_change_with_spec() -> None:
    problem = load_problem(_YAML)
    n1 = narrative_hash(problem.narrative)
    v1 = verification_hash(problem.verification)
    assert n1 == narrative_hash(problem.narrative)
    assert v1 == verification_hash(problem.verification)
    assert n1 != narrative_hash(problem.narrative + " extra")
    tweaked = dict(
        make_records(_score("x"), problem, ["a"])[0]
    )
    del tweaked  # records exist
    from dataclasses import replace
    from fractions import Fraction

    from dubito.problem import LinearConstraint

    ir = problem.verification
    assert ir is not None
    wood = ir.constraints[0]
    new_wood = LinearConstraint(wood.name, wood.terms, wood.op, Fraction(13))
    new_ir = replace(ir, constraints=(new_wood, *ir.constraints[1:]))
    assert verification_hash(new_ir) != v1
