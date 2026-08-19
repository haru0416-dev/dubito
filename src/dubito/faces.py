"""MCP-style tool descriptors for the same functions the CLI already runs.

No MCP SDK. `python -m dubito tools` prints these descriptors. `evaluate_tool`
is the function layer; `call_tool` wraps it in an ok/error envelope so an
external model never sees a traceback as the only signal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from dubito.agent import (
    INSTRUCTIONS,
    formulation_contract,
    playbook,
    score_for_agent,
    spec_for_agent,
)
from dubito.archive import read_archive
from dubito.cegis import PathMapReformulator, parse_replacements, run_cegis
from dubito.lessons import distill
from dubito.problem import load_problem
from dubito.router import capabilities, route

_TOOL_CHECK = (
    "Verify independently written formulation() modules against a problem YAML. "
    "Default compact=true returns agent.next / agent.repair / agent.ceiling. "
    "Do not compile the YAML verification block into the solvers. "
    "agree is not a global proof."
)
_TOOL_SPEC = (
    "Return the narrative, canonical variable names, class, and verification "
    "ceiling. Does not include the verification IR. Call this before writing "
    "formulations."
)
_TOOL_CONTRACT = (
    "Return the formulation() module contract and a skeleton for one adapter. "
    "Fill constraints from the narrative only."
)

TOOLS: list[dict[str, object]] = [
    {
        "name": "dubito_playbook",
        "description": (
            "How to use dubito as an external-model tool: spec → contract → "
            "two independent modules → check → repair. No in-process LLM."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "dubito_spec",
        "description": _TOOL_SPEC,
        "inputSchema": {
            "type": "object",
            "properties": {
                "problem": {"type": "string", "description": "Path to dubito.problem/v1 YAML"},
                "n_formulations": {
                    "type": "integer",
                    "default": 2,
                    "description": "How many formulation modules you plan to check (affects exchange)",
                },
            },
            "required": ["problem"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "dubito_contract",
        "description": _TOOL_CONTRACT,
        "inputSchema": {
            "type": "object",
            "properties": {
                "problem": {"type": "string", "description": "Path to problem YAML (preferred)"},
                "class": {
                    "type": "string",
                    "description": "Problem class if you do not have a YAML yet",
                },
            },
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "dubito_profile",
        "description": (
            "Dump which verification layers will run and the strength ceiling. "
            "Does not choose a solver and does not run solvers."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "problem": {"type": "string"},
                "n_formulations": {"type": "integer", "default": 0},
                "check_dual": {"type": "boolean", "default": True},
                "check_properties": {"type": "boolean", "default": True},
            },
            "required": ["problem"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "dubito_check",
        "description": _TOOL_CHECK,
        "inputSchema": {
            "type": "object",
            "properties": {
                "problem": {"type": "string", "description": "Path to problem YAML"},
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Python modules exporting formulation()",
                },
                "archive": {"type": "string", "description": "Optional JSONL archive path"},
                "check_dual": {"type": "boolean", "default": True},
                "check_properties": {"type": "boolean", "default": True},
                "compact": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true (default), omit exchanges/profile; keep agent brief",
                },
            },
            "required": ["problem", "paths"],
        },
    },
    {
        "name": "dubito_cegis",
        "description": (
            "Verify, archive counterexamples, apply a path-map Reformulator, repeat. "
            "No in-process LLM. After you rewrite a file, prefer dubito_check."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "problem": {"type": "string"},
                "paths": {"type": "array", "items": {"type": "string"}},
                "max_iters": {"type": "integer", "default": 5},
                "archive": {"type": "string"},
                "replace": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "SRC=DST path maps for tests, not an LLM",
                },
                "check_dual": {"type": "boolean", "default": True},
                "check_properties": {"type": "boolean", "default": True},
                "compact": {"type": "boolean", "default": True},
            },
            "required": ["problem", "paths"],
        },
    },
    {
        "name": "dubito_archive",
        "description": "Read a dubito.archive/v1 JSONL file.",
        "inputSchema": {
            "type": "object",
            "properties": {"archive": {"type": "string"}},
            "required": ["archive"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "dubito_lessons",
        "description": (
            "Distill an archive into dubito.lessons/v1 grouped counts. "
            "Use as repair memory; do not paste verification IR into prompts."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"archive": {"type": "string"}},
            "required": ["archive"],
        },
        "annotations": {"readOnlyHint": True},
    },
]


def tool_descriptors() -> list[dict[str, object]]:
    return list(TOOLS)


def instructions() -> str:
    return INSTRUCTIONS


def call_tool(name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, object]:
    """Envelope around evaluate_tool. Never raises to the MCP host."""

    try:
        result = evaluate_tool(name, arguments)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 — tool host must stay alive
        message = str(exc)
        if isinstance(exc, SystemExit) and exc.code not in (0, None, True, False):
            message = str(exc.code) if not isinstance(exc.code, int) else (message or "SystemExit")
        return {
            "ok": False,
            "tool": name,
            "result": None,
            "error": {"type": type(exc).__name__, "message": message},
        }
    return {"ok": True, "tool": name, "result": result, "error": None}


def evaluate_tool(name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, object]:
    """Dispatch a tool name to the same functions the CLI uses."""

    args = dict(arguments or {})
    if name == "dubito_playbook":
        return playbook()
    if name == "dubito_spec":
        problem = load_problem(args["problem"])
        return spec_for_agent(problem, n_formulations=int(args.get("n_formulations", 2)))
    if name == "dubito_contract":
        if args.get("problem"):
            return formulation_contract(load_problem(args["problem"]))
        if args.get("class"):
            return formulation_contract(problem_class=str(args["class"]))
        raise ValueError("dubito_contract requires problem or class")
    if name == "dubito_check":
        from dubito.cli import run_check

        score = run_check(
            [Path(item) for item in args["paths"]],
            problem_path=Path(args["problem"]),
            archive_path=Path(args["archive"]) if args.get("archive") else None,
            check_dual=bool(args.get("check_dual", True)),
            check_properties=bool(args.get("check_properties", True)),
        )
        compact = bool(args["compact"]) if "compact" in args else True
        payload = score_for_agent(score, compact=compact)
        if args.get("archive"):
            lessons = distill(read_archive(args["archive"]))
            seen = {
                str(item["kind"]): int(item["count"])
                for item in lessons.get("lessons", [])
                if item.get("problem_id") == score.problem_id
            }
            if seen and isinstance(payload.get("agent"), dict):
                payload["agent"]["seen_kinds"] = {
                    kind: seen[kind]
                    for kind in payload["agent"].get("kinds", [])
                    if kind in seen
                }
        return payload
    if name == "dubito_cegis":
        problem = load_problem(args["problem"])
        mapping = parse_replacements(list(args.get("replace") or []))
        reformulator = PathMapReformulator(mapping) if mapping else None
        result = run_cegis(
            problem,
            [Path(item) for item in args["paths"]],
            reformulator=reformulator,
            max_iters=int(args.get("max_iters", 5)),
            archive_path=args.get("archive"),
            check_dual=bool(args.get("check_dual", True)),
            check_properties=bool(args.get("check_properties", True)),
        )
        compact = bool(args["compact"]) if "compact" in args else True
        payload = result.to_dict()
        payload["score"] = score_for_agent(result.score, compact=compact)
        return payload
    if name == "dubito_archive":
        return {"schema": "dubito.archive/v1", "records": read_archive(args["archive"])}
    if name == "dubito_lessons":
        return distill(read_archive(args["archive"]))
    if name == "dubito_profile":
        problem = load_problem(args["problem"])
        routed = route(
            problem,
            check_dual=bool(args.get("check_dual", True)),
            check_properties=bool(args.get("check_properties", True)),
            n_formulations=int(args.get("n_formulations", 0)),
        )
        payload = routed.to_dict()
        payload["capabilities"] = list(capabilities(problem.problem_class))
        payload["determinism"] = {"seed": problem.determinism.seed}
        payload["instructions"] = INSTRUCTIONS
        return payload
    raise KeyError(f"unknown tool {name!r}")
