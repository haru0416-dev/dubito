from __future__ import annotations

from pathlib import Path

from dubito.dual import check_dual
from dubito.load import load_formulation
from dubito.pipeline import verify
from dubito.problem import load_problem
from dubito.selfcheck import run_self_probe

_SELF = Path(__file__).resolve().parents[1] / "probes/self"
_FURNITURE = Path(__file__).resolve().parents[1] / "probes/phase0/furniture.yaml"
_DUAL = _SELF / "dual.yaml"
_NEIGHBOR = _SELF / "neighborhood.yaml"


def test_self_formulations_do_not_import_ir() -> None:
    for path in (
        _SELF / "formulations/dual_cvxpy.py",
        _SELF / "formulations/dual_ortools.py",
        _SELF / "formulations/neighborhood_cvxpy.py",
        _SELF / "formulations/neighborhood_ortools.py",
    ):
        src = path.read_text()
        assert "furniture.yaml" not in src
        assert "dual.yaml" not in src
        assert "neighborhood.yaml" not in src
        assert "as_linear_ir" not in src
        assert "from dubito.dual" not in src
        assert "import dubito.dual" not in src
        assert "ortools" not in src or "cvxpy" not in src


def test_cvxpy_integer_check_accepts_python_float() -> None:
    """Integer vars without nonneg used to reject a Python float in CVXPY 1.9."""

    checked = load_formulation(_SELF / "formulations/neighborhood_cvxpy.py").check(
        {"tables": 2.0, "chairs": 6.0},
        load_problem(_NEIGHBOR).tolerances,
    )
    assert checked.feasible
    assert checked.integrality_ok
    assert checked.objective is not None
    assert abs(checked.objective - 220.0) < 1e-6


def test_independent_dual_agrees_at_220() -> None:
    score = verify(
        [
            load_formulation(_SELF / "formulations/dual_cvxpy.py"),
            load_formulation(_SELF / "formulations/dual_ortools.py"),
        ],
        load_problem(_DUAL),
    )
    assert score.verdict == "agree"
    assert score.layers["dual"] == "ran"
    assert all(abs(float(value) - 220.0) < 1e-6 for value in score.objective.values())


def test_scipy_dual_prices_are_feasible_in_independent_encodings() -> None:
    furniture = load_problem(_FURNITURE)
    report = check_dual(
        furniture,
        {"ok": 220.0},
        assignments={"ok": {"tables": 2.0, "chairs": 6.0}},
    )
    assert report.dual_assignment is not None
    prices = {
        "wood_price": float(report.dual_assignment["wood"]),
        "labor_price": float(report.dual_assignment["labor"]),
        "mix_price": float(report.dual_assignment["mix"]),
    }
    problem = load_problem(_DUAL)
    for path in (
        _SELF / "formulations/dual_cvxpy.py",
        _SELF / "formulations/dual_ortools.py",
    ):
        checked = load_formulation(path).check(prices, problem.tolerances)
        assert checked.feasible, checked.violations
        assert checked.objective is not None
        assert abs(checked.objective - 220.0) < 1e-5


def test_inverted_dual_cover_is_caught() -> None:
    score = verify(
        [
            load_formulation(_SELF / "formulations/dual_cvxpy.py"),
            load_formulation(_SELF / "bugs/dual_inverted_cover.py"),
        ],
        load_problem(_DUAL),
    )
    assert score.verdict == "disagree"


def test_neighborhood_agrees_at_incumbent() -> None:
    score = verify(
        [
            load_formulation(_SELF / "formulations/neighborhood_cvxpy.py"),
            load_formulation(_SELF / "formulations/neighborhood_ortools.py"),
        ],
        load_problem(_NEIGHBOR),
    )
    assert score.verdict == "agree"
    for assignment in (
        load_formulation(_SELF / "formulations/neighborhood_cvxpy.py").solve().assignment,
        load_formulation(_SELF / "formulations/neighborhood_ortools.py").solve().assignment,
    ):
        assert round(assignment["tables"]) == 2
        assert round(assignment["chairs"]) == 6


def test_neighborhood_inverted_mix_is_caught() -> None:
    score = verify(
        [
            load_formulation(_SELF / "formulations/neighborhood_cvxpy.py"),
            load_formulation(_SELF / "bugs/neighborhood_inverted_mix.py"),
        ],
        load_problem(_NEIGHBOR),
    )
    assert score.verdict == "disagree"


def test_self_probe_hypothesis_holds() -> None:
    payload = run_self_probe()
    assert payload["hypothesis_holds"] is True
    assert payload["false_disagreement"] == 0
    assert payload["false_agreement"] == 0
    assert payload["bound_matches"] is True
    assert payload["scipy_prices_feasible_in_independent"] is True
