from __future__ import annotations

import json
import os
from pathlib import Path

from dubito.exchange import exchange_check
from dubito.load import load_formulation
from dubito.model import ScoreVector, Tolerances
from dubito.pipeline import verify
from dubito.problem import load_problem

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PEER = _REPO_ROOT / "probes/phase0/formulations/ortools_ok.py"
_DEFAULT_PROBLEM = _REPO_ROOT / "probes/phase0/furniture.yaml"


def evaluate(program_path: str) -> dict[str, float]:
    """OpenEvolve-compatible fitness function.

    The program under evaluation must export `formulation()`. Peers are loaded
    from DUBITO_PEER_FORMULATIONS (comma-separated paths). Combined score is 1
    only when the pipeline verdict is `agree`.
    """

    score = evaluate_score(program_path)
    smt_values = list(score.smt_feasible.values())
    smt_obj = list(score.smt_objective_match.values())
    smt_ok = 1.0
    if smt_values:
        smt_ok = 1.0 if all(smt_values) and all(item is not False for item in smt_obj) else 0.0
    return {
        "combined_score": 1.0 if score.verdict == "agree" else 0.0,
        "agreement": float(score.agreement),
        "all_feasible": 1.0 if score.feasible and all(score.feasible.values()) else 0.0,
        "optima_match": 1.0 if score.claimed_optima_match else 0.0,
        "smt_ok": smt_ok,
        "n_counterexamples": float(len(score.counterexamples)),
    }


def evaluate_score(program_path: str) -> ScoreVector:
    candidate = load_formulation(program_path)
    peers = _peer_paths()
    formulations = [candidate]
    for peer in peers:
        if Path(peer).resolve() == Path(program_path).resolve():
            continue
        formulations.append(load_formulation(peer))
    problem_path = _problem_path()
    if problem_path is not None:
        return verify(formulations, load_problem(problem_path))
    if len(formulations) < 2:
        raise RuntimeError(
            "evaluator needs a problem YAML (DUBITO_PROBLEM) or at least one peer formulation"
        )
    return exchange_check(formulations, tol=Tolerances(), problem_id=candidate.problem_id)


def _peer_paths() -> list[str]:
    raw = os.environ.get("DUBITO_PEER_FORMULATIONS", "")
    if raw.strip():
        return [item.strip() for item in raw.split(",") if item.strip()]
    if _DEFAULT_PEER.is_file():
        return [str(_DEFAULT_PEER)]
    return []


def _problem_path() -> Path | None:
    raw = os.environ.get("DUBITO_PROBLEM", "")
    if raw.strip():
        return Path(raw)
    if _DEFAULT_PROBLEM.is_file():
        return _DEFAULT_PROBLEM
    return None


def evaluate_with_artifacts(program_path: str) -> dict[str, object]:
    """Same metrics plus a JSON score vector for OpenEvolve artifacts."""

    score = evaluate_score(program_path)
    metrics = evaluate(program_path)
    return {
        "metrics": metrics,
        "artifacts": {"score_vector": json.dumps(score.to_dict(), sort_keys=True, default=str)},
    }
