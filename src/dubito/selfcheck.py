"""Apply dubito to the LPs already inside dubito.

Does not compile the furniture YAML into solvers. Independent encodings of
the verification-IR dual and of the local-optimality box are checked with
the same pipeline as any other probe. SciPy's dual.py result is then
substituted into those encodings.
"""

from __future__ import annotations

from pathlib import Path

from dubito.dual import check_dual
from dubito.load import load_formulation
from dubito.numeric import numbers_close
from dubito.pipeline import verify
from dubito.problem import load_problem

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SELF = _REPO_ROOT / "probes/self"
_FURNITURE = _REPO_ROOT / "probes/phase0/furniture.yaml"
_EXPECTED_BOUND = 220.0


def run_self_probe() -> dict[str, object]:
    """Cross-check dual.py and local_optimality against independent formulations."""

    dual_problem = load_problem(_SELF / "dual.yaml")
    neighborhood_problem = load_problem(_SELF / "neighborhood.yaml")
    furniture = load_problem(_FURNITURE)
    scipy_report = check_dual(
        furniture,
        {"incumbent": _EXPECTED_BOUND},
        assignments={"incumbent": {"tables": 2.0, "chairs": 6.0}},
    )

    cases = [
        {
            "id": "dual-ok-vs-ok",
            "expect": "agree",
            "problem": dual_problem,
            "paths": [
                _SELF / "formulations/dual_cvxpy.py",
                _SELF / "formulations/dual_ortools.py",
            ],
            "why": "Independent GLPK and GLOP encodings of the furniture dual should close at 220.",
        },
        {
            "id": "dual-inverted-cover",
            "expect": "disagree",
            "problem": dual_problem,
            "paths": [
                _SELF / "formulations/dual_cvxpy.py",
                _SELF / "bugs/dual_inverted_cover.py",
            ],
            "why": "Covering inequalities flipped to <=. Zero prices claim 0; SMT must disagree.",
        },
        {
            "id": "neighborhood-ok-vs-ok",
            "expect": "agree",
            "problem": neighborhood_problem,
            "paths": [
                _SELF / "formulations/neighborhood_cvxpy.py",
                _SELF / "formulations/neighborhood_ortools.py",
            ],
            "why": "Local-opt box around (2, 6) should still have profit 220.",
        },
        {
            "id": "neighborhood-inverted-mix",
            "expect": "disagree",
            "problem": neighborhood_problem,
            "paths": [
                _SELF / "formulations/neighborhood_cvxpy.py",
                _SELF / "bugs/neighborhood_inverted_mix.py",
            ],
            "why": "Mix inverted inside the box. Exchange / SMT must flag it.",
        },
    ]

    results: list[dict[str, object]] = []
    detections = 0
    false_agreement = 0
    false_disagreement = 0
    dual_objectives: dict[str, float | None] = {}
    for case in cases:
        score = verify(list(map(load_formulation, case["paths"])), case["problem"])
        detected = score.verdict == case["expect"]
        if case["expect"] == "disagree" and detected:
            detections += 1
        if case["expect"] == "agree" and score.verdict != "agree":
            false_disagreement += 1
        if case["expect"] == "disagree" and score.verdict == "agree":
            false_agreement += 1
        if case["id"] == "dual-ok-vs-ok":
            dual_objectives = dict(score.objective)
        results.append(
            {
                "id": case["id"],
                "expect": case["expect"],
                "why": case["why"],
                "detected": detected,
                "verdict": score.verdict,
                "verification_strength": score.verification_strength,
                "objective": dict(score.objective),
                "score": score.to_dict(),
            }
        )

    prices = _prices_from_scipy(scipy_report.dual_assignment)
    scipy_in_independent: dict[str, object] = {}
    scipy_feasible = True
    for path in (
        _SELF / "formulations/dual_cvxpy.py",
        _SELF / "formulations/dual_ortools.py",
    ):
        formulation = load_formulation(path)
        checked = formulation.check(prices, dual_problem.tolerances)
        scipy_in_independent[formulation.name] = {
            "feasible": checked.feasible,
            "objective": checked.objective,
            "violations": [item.to_dict() for item in checked.violations],
        }
        if not checked.feasible:
            scipy_feasible = False
        if not numbers_close(checked.objective, _EXPECTED_BOUND, dual_problem.tolerances):
            scipy_feasible = False

    bound_matches = bool(
        dual_objectives
        and scipy_report.bound is not None
        and numbers_close(scipy_report.bound, _EXPECTED_BOUND, furniture.tolerances)
        and all(
            numbers_close(value, _EXPECTED_BOUND, dual_problem.tolerances)
            for value in dual_objectives.values()
            if value is not None
        )
    )
    bug_cases = sum(1 for case in cases if case["expect"] == "disagree")
    hypothesis_holds = (
        false_disagreement == 0
        and false_agreement == 0
        and detections == bug_cases
        and bound_matches
        and scipy_feasible
        and scipy_report.complementary_slackness.get("incumbent") is True
    )
    return {
        "probe": "self-application",
        "hypothesis": (
            "Internal LPs (verification-IR dual, local-optimality box) agree "
            "across independent formulations and match dual.py's SciPy bound."
        ),
        "hypothesis_holds": hypothesis_holds,
        "detections": detections,
        "bug_cases": bug_cases,
        "false_disagreement": false_disagreement,
        "false_agreement": false_agreement,
        "scipy_bound": scipy_report.bound,
        "scipy_status": scipy_report.status,
        "scipy_dual_assignment": dict(scipy_report.dual_assignment or {}),
        "independent_dual_objectives": dual_objectives,
        "bound_matches": bound_matches,
        "scipy_prices_feasible_in_independent": scipy_feasible,
        "scipy_in_independent": scipy_in_independent,
        "skipped": {
            "router": "Class-profile lookup, not a budgeted optimizer.",
        },
        "cases": results,
    }


def _prices_from_scipy(assignment: dict[str, float] | None) -> dict[str, float]:
    raw = assignment or {}
    return {
        "wood_price": float(raw.get("wood", 0.0)),
        "labor_price": float(raw.get("labor", 0.0)),
        "mix_price": float(raw.get("mix", 0.0)),
    }
