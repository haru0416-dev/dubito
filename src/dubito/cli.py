from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dubito.exchange import exchange_check
from dubito.load import load_formulation
from dubito.score import score_to_json
from dubito.model import Formulation, ScoreVector, Tolerances

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE0 = _REPO_ROOT / "probes/phase0"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dubito",
        description="Cross-check independently formulated solver encodings.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check", help="Exchange-check formulation modules")
    check.add_argument("paths", nargs="+", type=Path, help="Python modules exporting formulation()")
    check.add_argument("--problem-id", default=None)
    check.add_argument("--indent", type=int, default=2)

    probe = sub.add_parser("probe", help="Run the Phase 0 planted-bug probe")
    probe.add_argument("--indent", type=int, default=2)

    args = parser.parse_args(argv)
    if args.cmd == "check":
        score = _run_check(args.paths, problem_id=args.problem_id)
        print(score_to_json(score, indent=args.indent))
        return 0 if score.verdict == "agree" else 1
    if args.cmd == "probe":
        payload = run_phase0_probe()
        print(json.dumps(payload, indent=args.indent, sort_keys=True))
        hypothesis_ok = bool(payload["hypothesis_holds"])
        return 0 if hypothesis_ok else 2
    raise AssertionError(args.cmd)


def _run_check(paths: list[Path], problem_id: str | None) -> ScoreVector:
    formulations: list[Formulation] = [load_formulation(path) for path in paths]
    return exchange_check(formulations, tol=Tolerances(), problem_id=problem_id)


def run_phase0_probe() -> dict[str, object]:
    """Run the Phase 0 cases: independent OK pair + planted formulation bugs."""

    formulations = _PHASE0 / "formulations"
    bugs = _PHASE0 / "bugs"
    cases = [
        {
            "id": "ok-vs-ok",
            "expect": "agree",
            "paths": [
                formulations / "cvxpy_ok.py",
                formulations / "ortools_ok.py",
            ],
            "why": "Independent CVXPY and OR-Tools encodings of the same narrative should agree.",
        },
        {
            "id": "inverted-ratio",
            "expect": "disagree",
            "paths": [
                formulations / "cvxpy_ok.py",
                bugs / "cvxpy_inverted_ratio.py",
            ],
            "why": "Marketing constraint inverted (tables >= 2*chairs). Exchange must flag it.",
        },
        {
            "id": "missing-labor",
            "expect": "disagree",
            "paths": [
                formulations / "cvxpy_ok.py",
                bugs / "ortools_missing_labor.py",
            ],
            "why": "Labor resource dropped. Claimed optima and reverse feasibility must disagree.",
        },
        {
            "id": "wrong-profit",
            "expect": "disagree",
            "paths": [
                formulations / "ortools_ok.py",
                bugs / "cvxpy_wrong_profit.py",
            ],
            "why": "Table profit 40 instead of 50. Objective mismatch must disagree.",
        },
    ]
    results: list[dict[str, object]] = []
    detections = 0
    false_agreement = 0
    false_disagreement = 0
    for case in cases:
        score = _run_check(case["paths"], problem_id="furniture-workshop-v1")
        detected = score.verdict == case["expect"]
        if case["expect"] == "disagree" and detected:
            detections += 1
        if case["expect"] == "agree" and score.verdict != "agree":
            false_disagreement += 1
        if case["expect"] == "disagree" and score.verdict == "agree":
            false_agreement += 1
        results.append(
            {
                "id": case["id"],
                "expect": case["expect"],
                "why": case["why"],
                "detected": detected,
                "score": score.to_dict(),
            }
        )
    bug_cases = sum(1 for case in cases if case["expect"] == "disagree")
    hypothesis_holds = (
        false_disagreement == 0 and false_agreement == 0 and detections == bug_cases
    )
    return {
        "probe": "phase0-exchange",
        "hypothesis": "Independent-formulation disagreement detects formulation bugs.",
        "hypothesis_holds": hypothesis_holds,
        "detections": detections,
        "bug_cases": bug_cases,
        "false_disagreement": false_disagreement,
        "false_agreement": false_agreement,
        "cases": results,
    }


if __name__ == "__main__":
    sys.exit(main())
