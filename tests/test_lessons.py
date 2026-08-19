from __future__ import annotations

from pathlib import Path

from dubito.archive import append_counterexamples, make_records
from dubito.faces import evaluate_tool, tool_descriptors
from dubito.lessons import LESSONS_SCHEMA, distill
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


def test_distill_groups_by_problem_kind_and_hash() -> None:
    problem = load_problem(_YAML)
    records = make_records(_score("smt_infeasible", "smt_infeasible", "dual_bound_exceeded"), problem, ["a"])
    payload = distill(records)
    assert payload["schema"] == LESSONS_SCHEMA
    assert payload["n_records"] == 3
    by_kind = {item["kind"]: item for item in payload["lessons"]}
    assert by_kind["smt_infeasible"]["count"] == 2
    assert by_kind["dual_bound_exceeded"]["count"] == 1
    assert by_kind["smt_infeasible"]["verification_hash"] == records[0]["verification_hash"]
    assert by_kind["smt_infeasible"]["sample_assignment"] == {"tables": 4.0, "chairs": 0.0}


def test_distill_path_roundtrip(tmp_path: Path) -> None:
    problem = load_problem(_YAML)
    archive = tmp_path / "cx.jsonl"
    append_counterexamples(archive, _score("local_optimality"), problem, ["ok", "bug"])
    payload = evaluate_tool("dubito_lessons", {"archive": str(archive)})
    assert payload["schema"] == LESSONS_SCHEMA
    assert payload["n_records"] == 1
    assert payload["lessons"][0]["kind"] == "local_optimality"
