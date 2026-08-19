from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Mapping

from dubito.model import (
    CheckResult,
    ConstraintViolation,
    Formulation,
    SolveResult,
    Tolerances,
)


class SandboxedFormulation(Formulation):
    """Run solve/check in a child process so native solver libs never mix."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(Path(path).resolve())
        meta = _run_worker({"op": "meta", "path": self._path})
        self.name = str(meta["name"])
        self.variables = tuple(meta["variables"])
        self.sense = meta["sense"]  # type: ignore[assignment]
        self.problem_id = str(meta["problem_id"])

    def solve(self) -> SolveResult:
        payload = _run_worker({"op": "solve", "path": self._path})
        return SolveResult(
            solver=str(payload["solver"]),
            status=payload["status"],  # type: ignore[arg-type]
            assignment={str(k): float(v) for k, v in dict(payload["assignment"]).items()},
            objective=_opt_float(payload["objective"]),
            runtime_ms=float(payload["runtime_ms"]),
            error=payload["error"],  # type: ignore[arg-type]
        )

    def check(self, assignment: Mapping[str, float], tol: Tolerances) -> CheckResult:
        payload = _run_worker(
            {
                "op": "check",
                "path": self._path,
                "assignment": dict(assignment),
                "tolerances": tol.to_dict(),
            }
        )
        violations = [
            ConstraintViolation(
                name=str(item["name"]),
                violation=float(item["violation"]),
                detail=item["detail"],  # type: ignore[arg-type]
            )
            for item in payload["violations"]
        ]
        return CheckResult(
            feasible=bool(payload["feasible"]),
            objective=_opt_float(payload["objective"]),
            violations=violations,
            integrality_ok=bool(payload["integrality_ok"]),
        )


def _opt_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _run_worker(message: dict[str, object]) -> dict[str, object]:
    proc = subprocess.run(
        [sys.executable, "-m", "dubito._sandbox_worker"],
        input=json.dumps(message),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or f"worker exit {proc.returncode}"
        raise RuntimeError(err)
    return json.loads(proc.stdout)
