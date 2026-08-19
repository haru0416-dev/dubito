"""MCP-style tool descriptors for the same functions the CLI already runs.

No MCP SDK. `python -m dubito tools` prints these descriptors. An external
host can wrap them; this module must not grow a second scoring path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from dubito.archive import read_archive
from dubito.cegis import PathMapReformulator, parse_replacements, run_cegis
from dubito.lessons import distill
from dubito.problem import load_problem
from dubito.router import capabilities, route

TOOLS: list[dict[str, object]] = [
    {
        "name": "dubito_check",
        "description": (
            "Verify independently written formulation modules against a "
            "dubito.problem/v1 YAML. The verification IR is not compiled into solvers."
        ),
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
            },
            "required": ["problem", "paths"],
        },
    },
    {
        "name": "dubito_cegis",
        "description": (
            "Verify, archive counterexamples, apply a path-map Reformulator, repeat. "
            "No in-process LLM."
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
                    "description": "SRC=DST path maps, repeatable",
                },
                "check_dual": {"type": "boolean", "default": True},
                "check_properties": {"type": "boolean", "default": True},
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
    },
    {
        "name": "dubito_lessons",
        "description": "Distill an archive into dubito.lessons/v1 grouped counts.",
        "inputSchema": {
            "type": "object",
            "properties": {"archive": {"type": "string"}},
            "required": ["archive"],
        },
    },
    {
        "name": "dubito_profile",
        "description": (
            "Dump the class verification route (which layers run, ceiling). "
            "Does not choose a solver."
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
    },
]


def tool_descriptors() -> list[dict[str, object]]:
    return list(TOOLS)


def evaluate_tool(name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, object]:
    """Dispatch a tool name to the same functions the CLI uses."""

    args = dict(arguments or {})
    if name == "dubito_check":
        from dubito.cli import run_check

        score = run_check(
            [Path(item) for item in args["paths"]],
            problem_path=Path(args["problem"]),
            archive_path=Path(args["archive"]) if args.get("archive") else None,
            check_dual=bool(args.get("check_dual", True)),
            check_properties=bool(args.get("check_properties", True)),
        )
        return score.to_dict()
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
        return result.to_dict()
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
        return payload
    raise KeyError(f"unknown tool {name!r}")
