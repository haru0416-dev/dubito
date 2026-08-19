from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dubito.cegis import PathMapReformulator, parse_replacements, run_cegis
from dubito.exchange import exchange_check
from dubito.faces import call_tool, evaluate_tool, tool_descriptors
from dubito.lessons import distill_path
from dubito.load import load_formulation
from dubito.pipeline import verify
from dubito.problem import load_problem
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

    check = sub.add_parser("check", help="Verify formulation modules (router selects layers)")
    check.add_argument("paths", nargs="+", type=Path, help="Python modules exporting formulation()")
    check.add_argument(
        "--problem",
        type=Path,
        default=None,
        help="Structured problem YAML (verification IR is consumed only by the verifier)",
    )
    check.add_argument("--problem-id", default=None)
    check.add_argument("--indent", type=int, default=2)
    check.add_argument("--archive", type=Path, default=None, help="Append counterexamples as JSONL")
    check.add_argument("--no-dual", action="store_true", help="Skip verification-IR dual bound")
    check.add_argument("--no-properties", action="store_true", help="Skip Hypothesis properties")

    probe = sub.add_parser("probe", help="Run the Phase 0 planted-bug probe")
    probe.add_argument("--indent", type=int, default=2)

    cegis = sub.add_parser("cegis", help="Verify, archive counterexamples, reformulate, repeat")
    cegis.add_argument("paths", nargs="+", type=Path, help="Python modules exporting formulation()")
    cegis.add_argument("--problem", type=Path, required=True)
    cegis.add_argument("--max-iters", type=int, default=5)
    cegis.add_argument("--archive", type=Path, default=None)
    cegis.add_argument(
        "--replace",
        action="append",
        default=[],
        metavar="SRC=DST",
        help="Reformulator mapping (repeatable). No LLM; path swap only.",
    )
    cegis.add_argument("--no-dual", action="store_true")
    cegis.add_argument("--no-properties", action="store_true")
    cegis.add_argument("--indent", type=int, default=2)

    profile = sub.add_parser("profile", help="Dump the class verification route (no solvers)")
    profile.add_argument("--problem", type=Path, required=True)
    profile.add_argument(
        "--formulations",
        type=int,
        default=0,
        dest="n_formulations",
        help="How many formulation modules would be passed to check (affects exchange)",
    )
    profile.add_argument("--no-dual", action="store_true")
    profile.add_argument("--no-properties", action="store_true")
    profile.add_argument("--indent", type=int, default=2)

    tools = sub.add_parser("tools", help="Print MCP-style tool descriptors (no SDK)")
    tools.add_argument("--indent", type=int, default=2)

    lessons = sub.add_parser("lessons", help="Distill archive JSONL to dubito.lessons/v1")
    lessons.add_argument("--archive", type=Path, required=True)
    lessons.add_argument("--indent", type=int, default=2)

    spec = sub.add_parser("spec", help="Agent-facing spec (narrative + variables; no verification IR)")
    spec.add_argument("--problem", type=Path, required=True)
    spec.add_argument("--formulations", type=int, default=2, dest="n_formulations")
    spec.add_argument("--indent", type=int, default=2)

    contract = sub.add_parser("contract", help="formulation() contract and skeleton")
    contract.add_argument("--problem", type=Path, default=None)
    contract.add_argument("--class", dest="problem_class", default=None)
    contract.add_argument("--indent", type=int, default=2)

    playbook = sub.add_parser("playbook", help="How an external model should call the tools")
    playbook.add_argument("--indent", type=int, default=2)

    call = sub.add_parser("call", help="Invoke one tool by name with JSON arguments")
    call.add_argument("name")
    call.add_argument("--args", default="{}", help="JSON object of tool arguments")
    call.add_argument("--indent", type=int, default=2)

    mcp = sub.add_parser("mcp", help="JSON-RPC MCP stdio server (no SDK)")

    args = parser.parse_args(argv)
    if args.cmd == "check":
        score = run_check(
            args.paths,
            problem_path=args.problem,
            problem_id=args.problem_id,
            archive_path=args.archive,
            check_dual=not args.no_dual,
            check_properties=not args.no_properties,
        )
        print(score_to_json(score, indent=args.indent))
        return 0 if score.verdict == "agree" else 1
    if args.cmd == "probe":
        payload = run_phase0_probe()
        print(json.dumps(payload, indent=args.indent, sort_keys=True))
        hypothesis_ok = bool(payload["hypothesis_holds"])
        return 0 if hypothesis_ok else 2
    if args.cmd == "cegis":
        result = run_cegis_cmd(
            args.paths,
            problem_path=args.problem,
            max_iters=args.max_iters,
            archive_path=args.archive,
            replacements=args.replace,
            check_dual=not args.no_dual,
            check_properties=not args.no_properties,
        )
        print(json.dumps(result.to_dict(), indent=args.indent, sort_keys=True, default=str))
        return 0 if result.status == "converged" else 1
    if args.cmd == "profile":
        payload = evaluate_tool(
            "dubito_profile",
            {
                "problem": str(args.problem),
                "n_formulations": args.n_formulations,
                "check_dual": not args.no_dual,
                "check_properties": not args.no_properties,
            },
        )
        print(json.dumps(payload, indent=args.indent, sort_keys=True))
        return 0
    if args.cmd == "tools":
        print(json.dumps(tool_descriptors(), indent=args.indent, sort_keys=True))
        return 0
    if args.cmd == "lessons":
        payload = distill_path(args.archive)
        print(json.dumps(payload, indent=args.indent, sort_keys=True, default=str))
        return 0
    if args.cmd == "spec":
        payload = evaluate_tool(
            "dubito_spec",
            {"problem": str(args.problem), "n_formulations": args.n_formulations},
        )
        print(json.dumps(payload, indent=args.indent, sort_keys=True))
        return 0
    if args.cmd == "contract":
        arguments: dict[str, object] = {}
        if args.problem is not None:
            arguments["problem"] = str(args.problem)
        if args.problem_class is not None:
            arguments["class"] = args.problem_class
        envelope = call_tool("dubito_contract", arguments)
        print(json.dumps(envelope["result"] if envelope["ok"] else envelope, indent=args.indent, sort_keys=True))
        return 0 if envelope["ok"] else 2
    if args.cmd == "playbook":
        print(json.dumps(evaluate_tool("dubito_playbook"), indent=args.indent, sort_keys=True))
        return 0
    if args.cmd == "call":
        try:
            raw_args = json.loads(args.args)
        except json.JSONDecodeError as exc:
            print(json.dumps({"ok": False, "error": {"type": "JSONDecodeError", "message": str(exc)}}))
            return 2
        if not isinstance(raw_args, dict):
            print(json.dumps({"ok": False, "error": {"message": "--args must be a JSON object"}}))
            return 2
        envelope = call_tool(args.name, raw_args)
        print(json.dumps(envelope, indent=args.indent, sort_keys=True, default=str))
        return 0 if envelope["ok"] else 1
    if args.cmd == "mcp":
        from dubito.mcp import serve

        serve()
        return 0
    raise AssertionError(args.cmd)


def run_check(
    paths: list[Path],
    *,
    problem_path: Path | None = None,
    problem_id: str | None = None,
    archive_path: Path | None = None,
    check_dual: bool = True,
    check_properties: bool = True,
) -> ScoreVector:
    formulations: list[Formulation] = [load_formulation(path) for path in paths]
    if problem_path is not None:
        problem = load_problem(problem_path)
        return verify(
            formulations,
            problem,
            check_dual=check_dual,
            check_properties=check_properties,
            archive_path=archive_path,
        )
    if archive_path is not None:
        raise SystemExit("--archive requires --problem")
    if len(formulations) < 2:
        raise SystemExit("check without --problem needs at least two formulation modules")
    return exchange_check(formulations, tol=Tolerances(), problem_id=problem_id)


def run_cegis_cmd(
    paths: list[Path],
    *,
    problem_path: Path,
    max_iters: int,
    archive_path: Path | None,
    replacements: list[str],
    check_dual: bool,
    check_properties: bool,
):
    problem = load_problem(problem_path)
    mapping = parse_replacements(replacements)
    reformulator = PathMapReformulator(mapping) if mapping else None
    return run_cegis(
        problem,
        paths,
        reformulator=reformulator,
        max_iters=max_iters,
        archive_path=archive_path,
        check_dual=check_dual,
        check_properties=check_properties,
    )


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
        score = run_check(case["paths"], problem_id="furniture-workshop-v1")
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
