from __future__ import annotations

import json
from pathlib import Path

from dubito.cli import main
from dubito.faces import evaluate_tool, tool_descriptors


def test_tool_descriptors_cover_check_and_profile() -> None:
    names = {item["name"] for item in tool_descriptors()}
    assert "dubito_check" in names
    assert "dubito_spec" in names
    assert "dubito_playbook" in names
    assert "dubito_profile" in names
    for item in tool_descriptors():
        assert "inputSchema" in item
        assert item["inputSchema"]["type"] == "object"


def test_profile_tool_does_not_need_solvers() -> None:
    yaml_path = Path(__file__).resolve().parents[1] / "probes/phase0/furniture.yaml"
    payload = evaluate_tool(
        "dubito_profile",
        {"problem": str(yaml_path), "n_formulations": 2},
    )
    assert payload["class"] == "milp"
    assert payload["status"]["exchange"] == "pending"
    assert payload["status"]["smt"] == "pending"
    assert payload["status"]["dual"] == "pending"
    assert "cvxpy" in payload["capabilities"]
    assert payload["determinism"]["seed"] == 0


def test_nlp_profile_omits_smt() -> None:
    yaml_path = Path(__file__).resolve().parents[1] / "probes/phase3/rosenbrock.yaml"
    payload = evaluate_tool(
        "dubito_profile",
        {"problem": str(yaml_path), "n_formulations": 2},
    )
    assert payload["class"] == "nlp"
    assert payload["status"]["residual"] == "pending"
    assert "smt" not in payload["status"]
    assert "dual" not in payload["status"]


def test_cli_tools_prints_json(capsys) -> None:
    assert main(["tools", "--indent", "0"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert payload[0]["name"].startswith("dubito_")


def test_cli_spec_hides_ir(capsys) -> None:
    yaml_path = Path(__file__).resolve().parents[1] / "probes/phase0/furniture.yaml"
    assert main(["spec", "--problem", str(yaml_path), "--indent", "0"]) == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["id"] == "furniture-workshop-v1"
    assert "constraints" not in payload
    assert '"terms"' not in out


def test_cli_profile_furniture(capsys) -> None:
    yaml_path = Path(__file__).resolve().parents[1] / "probes/phase0/furniture.yaml"
    assert main(["profile", "--problem", str(yaml_path), "--formulations", "2"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["class"] == "milp"
    assert payload["status"]["exchange"] == "pending"
