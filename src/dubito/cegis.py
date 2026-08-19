"""CEGIS loop: verify → archive counterexamples → reformulate → repeat.

No LLM lives in this process. A Reformulator maps formulation paths; the
default is identity (stall after the first disagreement). External agents
supply PathMapReformulator or their own implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal, Protocol, Sequence

from dubito.archive import append_counterexamples
from dubito.load import load_formulation
from dubito.model import Formulation, ScoreVector
from dubito.pipeline import verify
from dubito.problem import ProblemSpec

CegisStatus = Literal["converged", "stalled", "budget_exhausted"]
LoadFn = Callable[[Path], Formulation]


class Reformulator(Protocol):
    def reformulate(
        self,
        paths: list[Path],
        score: ScoreVector,
        counterexamples: list[dict[str, object]],
    ) -> list[Path]:
        ...


class IdentityReformulator:
    def reformulate(
        self,
        paths: list[Path],
        score: ScoreVector,
        counterexamples: list[dict[str, object]],
    ) -> list[Path]:
        return list(paths)


class PathMapReformulator:
    """Replace formulation files by resolved path or basename."""

    def __init__(self, mapping: dict[Path, Path] | dict[str, str]) -> None:
        self._by_resolved: dict[Path, Path] = {}
        self._by_name: dict[str, Path] = {}
        for src, dst in mapping.items():
            source = Path(src)
            dest = Path(dst)
            resolved = source.resolve() if source.exists() else source
            self._by_resolved[resolved] = dest
            self._by_name[source.name] = dest

    def reformulate(
        self,
        paths: list[Path],
        score: ScoreVector,
        counterexamples: list[dict[str, object]],
    ) -> list[Path]:
        del score, counterexamples
        out: list[Path] = []
        for path in paths:
            current = Path(path)
            key = current.resolve() if current.exists() else current
            if key in self._by_resolved:
                out.append(Path(self._by_resolved[key]))
            elif current.name in self._by_name:
                out.append(Path(self._by_name[current.name]))
            else:
                out.append(current)
        return out


@dataclass
class CegisResult:
    status: CegisStatus
    iterations: int
    paths: list[Path]
    score: ScoreVector
    history: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "iterations": self.iterations,
            "paths": [str(path) for path in self.paths],
            "score": self.score.to_dict(),
            "history": list(self.history),
        }


def parse_replacements(items: Sequence[str]) -> dict[Path, Path]:
    mapping: dict[Path, Path] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"--replace expects SRC=DST, got {item!r}")
        src, dst = item.split("=", 1)
        mapping[Path(src)] = Path(dst)
    return mapping


def run_cegis(
    problem: ProblemSpec,
    paths: Sequence[Path],
    *,
    reformulator: Reformulator | None = None,
    max_iters: int = 5,
    archive_path: Path | None = None,
    check_dual: bool = True,
    check_properties: bool = True,
    load_fn: LoadFn | None = None,
) -> CegisResult:
    if max_iters < 1:
        raise ValueError("max_iters must be >= 1")
    reformulator = reformulator or IdentityReformulator()
    load = load_fn or (lambda path: load_formulation(path))
    current = [Path(path) for path in paths]
    history: list[dict[str, object]] = []
    last_score: ScoreVector | None = None

    for iteration in range(1, max_iters + 1):
        formulations = [load(path) for path in current]
        score = verify(
            formulations,
            problem,
            check_dual=check_dual,
            check_properties=check_properties,
        )
        last_score = score
        history.append(
            {
                "iteration": iteration,
                "paths": [str(path) for path in current],
                "formulation_names": [form.name for form in formulations],
                "verdict": score.verdict,
                "n_counterexamples": len(score.counterexamples),
            }
        )
        if archive_path is not None:
            append_counterexamples(
                archive_path,
                score,
                problem,
                [form.name for form in formulations],
            )
        if score.verdict == "agree":
            return CegisResult(
                status="converged",
                iterations=iteration,
                paths=current,
                score=score,
                history=history,
            )
        nxt = [Path(path) for path in reformulator.reformulate(
            current, score, list(score.counterexamples)
        )]
        if _same_paths(nxt, current):
            return CegisResult(
                status="stalled",
                iterations=iteration,
                paths=current,
                score=score,
                history=history,
            )
        current = nxt

    assert last_score is not None
    return CegisResult(
        status="budget_exhausted",
        iterations=max_iters,
        paths=current,
        score=last_score,
        history=history,
    )


def _same_paths(left: list[Path], right: list[Path]) -> bool:
    def key(path: Path) -> str:
        return str(path.resolve()) if path.exists() else str(path)

    return [key(path) for path in left] == [key(path) for path in right]
