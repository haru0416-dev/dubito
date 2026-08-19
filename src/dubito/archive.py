"""Append-only counterexample archive (dubito.archive/v1).

Closes PLAN §7: one JSONL object per counterexample, hashed to the problem
narrative and verification IR so later CEGIS / knowledge injection can join
on spec identity rather than file path.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from dubito.model import ScoreVector
from dubito.problem import ProblemSpec, VerificationIR

ARCHIVE_SCHEMA = "dubito.archive/v1"


def narrative_hash(narrative: str) -> str:
    return _sha256(narrative)


def verification_hash(ir: VerificationIR | None) -> str:
    if ir is None:
        return _sha256("")
    payload = {
        "constraints": [
            {
                "name": constraint.name,
                "terms": {key: str(value) for key, value in sorted(constraint.terms.items())},
                "op": constraint.op,
                "rhs": str(constraint.rhs),
            }
            for constraint in ir.constraints
        ],
        "objective": {key: str(value) for key, value in sorted(ir.objective.items())},
    }
    return _sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def make_records(
    score: ScoreVector,
    problem: ProblemSpec,
    formulation_names: list[str],
    *,
    timestamp: str | None = None,
) -> list[dict[str, object]]:
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    n_hash = narrative_hash(problem.narrative)
    v_hash = verification_hash(problem.verification)
    records: list[dict[str, object]] = []
    for item in score.counterexamples:
        assignment = item.get("assignment") if isinstance(item, dict) else None
        kind = item.get("kind") if isinstance(item, dict) else None
        records.append(
            {
                "schema": ARCHIVE_SCHEMA,
                "problem_id": problem.id,
                "kind": kind,
                "assignment": assignment,
                "formulation_names": list(formulation_names),
                "verdict": score.verdict,
                "narrative_hash": n_hash,
                "verification_hash": v_hash,
                "timestamp": ts,
                "counterexample": item,
            }
        )
    return records


def append_counterexamples(
    path: str | Path,
    score: ScoreVector,
    problem: ProblemSpec,
    formulation_names: list[str],
    *,
    timestamp: str | None = None,
) -> int:
    records = make_records(
        score, problem, formulation_names, timestamp=timestamp
    )
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, default=str))
            handle.write("\n")
    return len(records)


def read_archive(path: str | Path) -> list[dict[str, object]]:
    file_path = Path(path)
    if not file_path.is_file():
        return []
    records: list[dict[str, object]] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
