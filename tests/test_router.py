from __future__ import annotations

from dubito.problem import parse_problem
from dubito.router import capabilities, route


def _milp() -> dict[str, object]:
    return {
        "id": "toy-milp",
        "class": "milp",
        "sense": "max",
        "variables": {"x": {"kind": "integer", "lower": 0}},
        "verification": {
            "constraints": [{"name": "c", "terms": {"x": 1}, "op": "<=", "rhs": 1}],
            "objective": {"terms": {"x": 1}},
        },
        "properties": {"local_optimality": {"radius": 1, "max_examples": 4}},
    }


def _nlp() -> dict[str, object]:
    return {
        "id": "toy-nlp",
        "class": "nlp",
        "sense": "min",
        "variables": {"x": {"kind": "continuous"}, "y": {"kind": "continuous"}},
        "verification": {
            "kind": "residual",
            "objective": {"expr": "(1 - x)**2 + (y - x**2)**2"},
        },
        "properties": {"local_optimality": {"radius": 0.1, "max_examples": 8}},
    }


def test_milp_route_pending_layers() -> None:
    routed = route(parse_problem(_milp()), n_formulations=2)
    assert routed.profile.problem_class == "milp"
    assert routed.status["exchange"] == "pending"
    assert routed.status["smt"] == "pending"
    assert routed.status["dual"] == "pending"
    assert routed.status["properties"] == "pending"
    assert routed.status["code"] == "pending"
    assert "residual" not in routed.status


def test_nlp_route_skips_smt_and_dual() -> None:
    routed = route(parse_problem(_nlp()), n_formulations=2)
    assert routed.status["exchange"] == "pending"
    assert routed.status["residual"] == "pending"
    assert routed.status["properties"] == "pending"
    assert routed.status["code"] == "pending"
    assert "smt" not in routed.status
    assert "dual" not in routed.status
    assert "local neighborhood" in routed.profile.ceiling or "residual" in routed.profile.ceiling


def test_single_formulation_skips_exchange() -> None:
    routed = route(parse_problem(_milp()), n_formulations=1)
    assert routed.status["exchange"] == "skipped:single-formulation"


def test_convex_skips_unimplemented_kkt() -> None:
    problem = parse_problem(
        {
            "id": "toy-convex",
            "class": "convex",
            "sense": "min",
            "variables": {"x": {"kind": "continuous"}},
            "verification": {"kind": "residual", "objective": {"expr": "x**2"}},
        }
    )
    routed = route(problem, n_formulations=2)
    assert routed.status["kkt"] == "skipped:not-implemented"
    assert routed.status["residual"] == "pending"
    assert routed.status["properties"] == "skipped:no-properties-block"


def test_flags_turn_layers_off() -> None:
    routed = route(
        parse_problem(_milp()),
        n_formulations=2,
        check_dual=False,
        check_properties=False,
    )
    assert routed.status["dual"] == "off"
    assert routed.status["properties"] == "off"
    assert routed.status["smt"] == "pending"


def test_capabilities_are_advisory() -> None:
    assert "scipy" in capabilities("nlp")
    assert "cvxpy" in capabilities("milp")
    assert "optuna" in capabilities("blackbox")
