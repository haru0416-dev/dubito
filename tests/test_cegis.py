from __future__ import annotations

from pathlib import Path

from dubito.archive import read_archive
from dubito.cegis import IdentityReformulator, PathMapReformulator, parse_replacements, run_cegis
from dubito.load import load_formulation
from dubito.problem import load_problem
from tests.fakes import FakeFormulation

_PHASE0 = Path(__file__).resolve().parents[1] / "probes/phase0"
_PROBLEM = _PHASE0 / "furniture.yaml"
_OK_CVXPY = _PHASE0 / "formulations/cvxpy_ok.py"
_OK_ORTOOLS = _PHASE0 / "formulations/ortools_ok.py"
_INVERTED = _PHASE0 / "bugs/cvxpy_inverted_ratio.py"


def _furniture_fake(name: str, tables: float, chairs: float, objective: float, **kwargs) -> FakeFormulation:
    return FakeFormulation(
        name,
        {"tables": tables, "chairs": chairs},
        objective,
        problem_id="furniture-workshop-v1",
        **kwargs,
    )


def test_parse_replacements() -> None:
    mapping = parse_replacements(["buggy.py=ok.py", "a/x.py=b/y.py"])
    assert mapping[Path("buggy.py")] == Path("ok.py")
    assert mapping[Path("a/x.py")] == Path("b/y.py")


def test_cegis_fake_converges_after_path_map(tmp_path: Path) -> None:
    problem = load_problem(_PROBLEM)
    good_p = tmp_path / "good.py"
    bad_p = tmp_path / "bad.py"
    good2_p = tmp_path / "good2.py"
    for path in (good_p, bad_p, good2_p):
        path.write_text("# dummy formulation path\n", encoding="utf-8")
    archive = tmp_path / "cx.jsonl"

    good = _furniture_fake(
        "good",
        2.0,
        6.0,
        220.0,
        rejected={(4.0, 0.0): "mix"},
        objective_at={(2.0, 6.0): 220.0, (4.0, 0.0): 200.0},
    )
    bad = _furniture_fake(
        "bad",
        4.0,
        0.0,
        200.0,
        rejected={(2.0, 6.0): "inverted"},
        objective_at={(4.0, 0.0): 200.0, (2.0, 6.0): 220.0},
    )
    good2 = _furniture_fake(
        "good2",
        2.0,
        6.0,
        220.0,
        rejected={(4.0, 0.0): "mix"},
        objective_at={(2.0, 6.0): 220.0},
    )

    def load_fn(path: Path) -> FakeFormulation:
        return {good_p.name: good, bad_p.name: bad, good2_p.name: good2}[path.name]

    result = run_cegis(
        problem,
        [good_p, bad_p],
        reformulator=PathMapReformulator({bad_p: good2_p}),
        max_iters=3,
        archive_path=archive,
        load_fn=load_fn,
    )
    assert result.status == "converged"
    assert result.iterations == 2
    assert result.score.verdict == "agree"
    assert result.history[0]["verdict"] == "disagree"
    records = read_archive(archive)
    assert records
    assert any(item["kind"] == "smt_infeasible" for item in records)


def test_cegis_identity_stalls(tmp_path: Path) -> None:
    problem = load_problem(_PROBLEM)
    good_p = tmp_path / "good.py"
    bad_p = tmp_path / "bad.py"
    good_p.write_text("#\n", encoding="utf-8")
    bad_p.write_text("#\n", encoding="utf-8")
    good = _furniture_fake("good", 2.0, 6.0, 220.0, rejected={(4.0, 0.0): "mix"})
    bad = _furniture_fake("bad", 4.0, 0.0, 200.0, rejected={(2.0, 6.0): "inverted"})

    def load_fn(path: Path) -> FakeFormulation:
        return {good_p.name: good, bad_p.name: bad}[path.name]

    result = run_cegis(
        problem,
        [good_p, bad_p],
        reformulator=IdentityReformulator(),
        max_iters=3,
        load_fn=load_fn,
    )
    assert result.status == "stalled"
    assert result.iterations == 1
    assert result.score.verdict == "disagree"


def test_cegis_real_solvers_replace_inverted() -> None:
    problem = load_problem(_PROBLEM)
    result = run_cegis(
        problem,
        [_OK_CVXPY, _INVERTED],
        reformulator=PathMapReformulator({_INVERTED: _OK_ORTOOLS}),
        max_iters=3,
        load_fn=load_formulation,
    )
    assert result.status == "converged"
    assert result.iterations == 2
    assert result.score.verdict == "agree"
    assert result.score.verification_strength == "code+exchange+smt+dual+properties"
