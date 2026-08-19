from __future__ import annotations

import json
from pathlib import Path

from dubito.agent import agent_brief, formulation_contract, spec_for_agent
from dubito.faces import call_tool, evaluate_tool, tool_descriptors
from dubito.model import ScoreVector, Tolerances
from dubito.problem import load_problem

_YAML = Path(__file__).resolve().parents[1] / "probes/phase0/furniture.yaml"


def test_spec_omits_verification_matrix() -> None:
    spec = spec_for_agent(load_problem(_YAML))
    assert spec["schema"] == "dubito.spec/v1"
    assert spec["id"] == "furniture-workshop-v1"
    assert spec["class"] == "milp"
    assert spec["sense"] == "max"
    assert "tables" in spec["variables"]
    assert spec["variables"]["tables"]["kind"] == "integer"
    assert "narrative" in spec and "workshop" in spec["narrative"].lower()
    assert "verification" not in spec
    assert "constraints" not in spec
    blob = json.dumps(spec)
    assert '"terms"' not in blob
    assert "Do not import" in spec["invariants"][0]


def test_contract_skeleton_has_factory_not_ir() -> None:
    contract = formulation_contract(load_problem(_YAML))
    assert contract["module_must_export"] == "formulation() -> Formulation"
    assert "def formulation()" in contract["skeleton"]
    assert any("as_linear_ir" in item for item in contract["forbidden"])
    assert "tables" in contract["variables"]
    assert "12" not in contract["skeleton"]
    assert "50" not in contract["skeleton"]


def test_playbook_states_the_loop() -> None:
    book = evaluate_tool("dubito_playbook")
    assert book["schema"] == "dubito.playbook/v1"
    assert "dubito_spec" in book["tools_order"]
    assert any("verification" in item.lower() for item in book["do_not"])


def test_agent_brief_stop_on_agree() -> None:
    score = ScoreVector(
        problem_id="p",
        verdict="agree",
        verification_strength="exchange",
        guarantee="ceiling text",
        feasible={"a": True},
        agreement=1.0,
        objective={"a": 1.0},
        optimality_status={"a": "optimal"},
        claimed_optima_match=True,
        counterexamples=[],
        runtime_ms={"a": 0.0},
        tolerances=Tolerances(),
        profile={"ceiling": "residual only"},
    )
    brief = agent_brief(score)
    assert brief["stop"] is True
    assert brief["next"][0]["action"] == "stop"
    assert brief["ceiling"] == "residual only"


def test_agent_brief_names_solver_to_rewrite() -> None:
    score = ScoreVector(
        problem_id="p",
        verdict="disagree",
        verification_strength="exchange+smt",
        guarantee="g",
        feasible={"cvxpy_ok": True, "buggy": True},
        agreement=0.0,
        objective={"cvxpy_ok": 220.0, "buggy": 200.0},
        optimality_status={"cvxpy_ok": "optimal", "buggy": "optimal"},
        claimed_optima_match=False,
        counterexamples=[
            {
                "kind": "smt_infeasible",
                "solver": "buggy",
                "assignment": {"tables": 4.0, "chairs": 0.0},
            }
        ],
        runtime_ms={"cvxpy_ok": 0.0, "buggy": 0.0},
        tolerances=Tolerances(),
        profile={"ceiling": "not a MILP certificate"},
    )
    brief = agent_brief(score)
    assert brief["stop"] is False
    assert brief["next"][0]["action"] == "rewrite_formulation"
    assert brief["next"][0]["solver"] == "buggy"
    assert "smt_infeasible" in brief["kinds"]


def test_call_tool_unknown_is_envelope() -> None:
    envelope = call_tool("dubito_nope", {})
    assert envelope["ok"] is False
    assert envelope["error"]["type"] == "KeyError"


def test_call_tool_spec() -> None:
    envelope = call_tool("dubito_spec", {"problem": str(_YAML)})
    assert envelope["ok"] is True
    assert envelope["result"]["schema"] == "dubito.spec/v1"


def test_tool_descriptors_include_agent_tools() -> None:
    names = {item["name"] for item in tool_descriptors()}
    assert {"dubito_playbook", "dubito_spec", "dubito_contract", "dubito_check"} <= names
    playbook = next(item for item in tool_descriptors() if item["name"] == "dubito_playbook")
    assert playbook["inputSchema"]["type"] == "object"
