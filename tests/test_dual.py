from __future__ import annotations

from pathlib import Path

import pytest

from dubito.dual import check_dual, lp_relaxation_objective
from dubito.problem import load_problem, parse_problem

_YAML = Path(__file__).resolve().parents[1] / "probes/phase0/furniture.yaml"


def test_furniture_dual_closes_at_known_optimum() -> None:
    problem = load_problem(_YAML)
    report = check_dual(
        problem,
        {"ok": 220.0},
        assignments={"ok": {"tables": 2.0, "chairs": 6.0}},
    )
    assert report.status == "optimal"
    assert report.bound == pytest.approx(220.0)
    assert report.lp_relaxation == pytest.approx(220.0)
    assert report.closed["ok"] is True
    assert report.exceeded["ok"] is False
    assert report.gap["ok"] == pytest.approx(0.0)
    assert report.complementary_slackness["ok"] is True


def test_claimed_240_exceeds_furniture_dual() -> None:
    problem = load_problem(_YAML)
    report = check_dual(problem, {"buggy": 240.0})
    assert report.bound == pytest.approx(220.0)
    assert report.exceeded["buggy"] is True
    assert report.closed["buggy"] is False
    assert report.gap["buggy"] == pytest.approx(-20.0)


def test_suboptimal_feasible_point_has_gap_not_exceed() -> None:
    problem = load_problem(_YAML)
    report = check_dual(
        problem,
        {"sub": 200.0},
        assignments={"sub": {"tables": 0.0, "chairs": 10.0}},
    )
    assert report.exceeded["sub"] is False
    assert report.closed["sub"] is False
    assert report.gap["sub"] == pytest.approx(20.0)


def test_min_sense_claimed_below_bound_exceeds() -> None:
    problem = parse_problem(
        {
            "id": "min-x",
            "class": "lp",
            "sense": "min",
            "variables": {"x": {"kind": "continuous", "lower": 0}},
            "verification": {
                "constraints": [{"name": "floor", "terms": {"x": 1}, "op": ">=", "rhs": 3}],
                "objective": {"terms": {"x": 1}},
            },
        }
    )
    closed = check_dual(problem, {"a": 3.0}, assignments={"a": {"x": 3.0}})
    assert closed.bound == pytest.approx(3.0)
    assert closed.closed["a"] is True
    assert closed.exceeded["a"] is False
    low = check_dual(problem, {"b": 2.0})
    assert low.exceeded["b"] is True


def test_lp_relaxation_matches_dual() -> None:
    problem = load_problem(_YAML)
    assert lp_relaxation_objective(problem) == pytest.approx(220.0)
