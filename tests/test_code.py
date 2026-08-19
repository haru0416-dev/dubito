from __future__ import annotations

from pathlib import Path

from dubito.code import inspect_source
from dubito.load import load_formulation
from dubito.pipeline import verify
from dubito.problem import load_problem

_PHASE0 = Path(__file__).resolve().parents[1] / "probes/phase0"
_OK = _PHASE0 / "formulations/cvxpy_ok.py"
_FROM_IR = _PHASE0 / "bugs/cvxpy_from_ir.py"


def test_ok_source_has_no_code_findings() -> None:
    findings = inspect_source(_OK, solver="cvxpy_ok", peer_stems={"ortools_ok"})
    assert findings == []


def test_ir_import_is_a_code_finding() -> None:
    findings = inspect_source(_FROM_IR, solver="cvxpy_from_ir", peer_stems=set())
    kinds = {item.kind for item in findings}
    assert "code_import" in kinds
    assert any("as_linear_ir" in item.detail or "dubito.problem" in item.detail for item in findings)


def test_peer_import_is_a_code_finding(tmp_path: Path) -> None:
    path = tmp_path / "copycat.py"
    path.write_text(
        "from cvxpy_ok import formulation\n",
        encoding="utf-8",
    )
    findings = inspect_source(path, solver="copycat", peer_stems={"cvxpy_ok"})
    assert any(item.kind == "code_peer_import" for item in findings)
    assert any(item.kind == "code_no_factory" for item in findings)


def test_from_ir_fails_verify_as_code() -> None:
    score = verify(
        [
            load_formulation(_PHASE0 / "formulations/ortools_ok.py"),
            load_formulation(_FROM_IR),
        ],
        load_problem(_PHASE0 / "furniture.yaml"),
    )
    assert score.layers["code"] == "ran"
    assert score.verdict == "disagree"
    assert score.agreement == 1.0
    assert any(item["kind"] == "code_import" for item in score.counterexamples)
