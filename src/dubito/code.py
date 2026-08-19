"""Static checks on formulation *source*. Does not execute solver code.

This is the code-verifier layer: catch IR imports and peer copies that would
make exchange+SMT look clean because every backend compiled the same matrix.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from dubito.model import Formulation

_FORBIDDEN_MODULES = (
    "dubito.problem",
    "dubito.dual",
    "dubito.ir",
    "dubito.z3check",
    "dubito.residual",
    "dubito.pipeline",
    "dubito.selfcheck",
    "yaml",
    "ruamel",
    "ruamel.yaml",
)
_FORBIDDEN_DUBITO_NAMES = frozenset(
    {
        "problem",
        "dual",
        "ir",
        "z3check",
        "residual",
        "pipeline",
        "selfcheck",
        "as_linear_ir",
        "as_residual_ir",
        "load_problem",
        "parse_problem",
    }
)
_FACTORY = "formulation"


@dataclass
class CodeFinding:
    kind: str
    solver: str
    path: str
    detail: str

    def to_counterexample(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "solver": self.solver,
            "path": self.path,
            "detail": self.detail,
        }


@dataclass
class CodeReport:
    ok: dict[str, bool] = field(default_factory=dict)
    findings: list[CodeFinding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": dict(self.ok),
            "findings": [item.to_counterexample() for item in self.findings],
            "notes": list(self.notes),
        }


def formulation_path(form: Formulation) -> Path | None:
    raw = getattr(form, "source_path", None) or getattr(form, "_path", None)
    if raw is None:
        return None
    return Path(str(raw))


def check_code(formulations: list[Formulation]) -> CodeReport:
    """AST-inspect loaded formulation modules. Skip forms with no source path."""

    report = CodeReport()
    paths = [(form, formulation_path(form)) for form in formulations]
    peer_stems = {
        path.stem for _, path in paths if path is not None and path.stem
    }
    any_source = False
    for form, path in paths:
        if path is None:
            report.notes.append(f"{form.name}: code check skipped (no source path)")
            continue
        any_source = True
        findings = inspect_source(
            path, solver=form.name, peer_stems=peer_stems - {path.stem}
        )
        report.findings.extend(findings)
        report.ok[form.name] = not findings
    if not any_source:
        report.notes.append("code check skipped: no formulation source paths")
    return report


def inspect_source(
    path: Path,
    *,
    solver: str,
    peer_stems: set[str] | None = None,
) -> list[CodeFinding]:
    findings: list[CodeFinding] = []
    resolved = path.resolve()
    if resolved.name == "types.py":
        findings.append(
            CodeFinding(
                kind="code_name",
                solver=solver,
                path=str(resolved),
                detail="do not name a module types.py (stdlib shadowing)",
            )
        )
    try:
        source = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        findings.append(
            CodeFinding(
                kind="code_parse",
                solver=solver,
                path=str(resolved),
                detail=f"could not read source: {exc}",
            )
        )
        return findings
    try:
        tree = ast.parse(source, filename=str(resolved))
    except SyntaxError as exc:
        findings.append(
            CodeFinding(
                kind="code_parse",
                solver=solver,
                path=str(resolved),
                detail=f"syntax error: {exc.msg} (line {exc.lineno})",
            )
        )
        return findings
    if not _has_factory(tree):
        findings.append(
            CodeFinding(
                kind="code_no_factory",
                solver=solver,
                path=str(resolved),
                detail="module must export formulation()",
            )
        )
    for module, name in _imports(tree):
        if _forbidden_module(module) or (
            module in {None, "dubito"} and name in _FORBIDDEN_DUBITO_NAMES
        ):
            findings.append(
                CodeFinding(
                    kind="code_import",
                    solver=solver,
                    path=str(resolved),
                    detail=f"forbidden import {module or '.'}:{name or '*'}",
                )
            )
        stem = (module or "").rsplit(".", 1)[-1]
        if name in (peer_stems or ()) or stem in (peer_stems or ()):
            findings.append(
                CodeFinding(
                    kind="code_peer_import",
                    solver=solver,
                    path=str(resolved),
                    detail=f"formulation imports peer module {name or module}",
                )
            )
    return findings


def _has_factory(tree: ast.AST) -> bool:
    for node in getattr(tree, "body", ()):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == _FACTORY:
            return True
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == _FACTORY:
                    return True
    return False


def _imports(tree: ast.AST) -> list[tuple[str | None, str | None]]:
    found: list[tuple[str | None, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, None))
        elif isinstance(node, ast.ImportFrom):
            module = node.module
            for alias in node.names:
                found.append((module, alias.name))
    return found


def _forbidden_module(module: str | None) -> bool:
    if not module:
        return False
    return any(
        module == prefix or module.startswith(prefix + ".")
        for prefix in _FORBIDDEN_MODULES
    )
