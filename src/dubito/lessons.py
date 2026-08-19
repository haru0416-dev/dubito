"""Distill dubito.archive/v1 JSONL into grouped lessons. No LLM."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from dubito.archive import read_archive

LESSONS_SCHEMA = "dubito.lessons/v1"


def distill(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Group archive rows by (problem_id, kind, verification_hash)."""

    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for record in records:
        key = (
            str(record.get("problem_id") or ""),
            str(record.get("kind") or ""),
            str(record.get("verification_hash") or ""),
        )
        groups.setdefault(key, []).append(record)

    lessons: list[dict[str, Any]] = []
    for (problem_id, kind, verification_hash), rows in sorted(groups.items()):
        verdicts = Counter(str(row.get("verdict") or "unknown") for row in rows)
        sample = next(
            (
                row.get("assignment")
                for row in rows
                if isinstance(row.get("assignment"), dict)
            ),
            None,
        )
        lessons.append(
            {
                "problem_id": problem_id,
                "kind": kind,
                "verification_hash": verification_hash,
                "narrative_hash": rows[0].get("narrative_hash"),
                "count": len(rows),
                "verdicts": dict(verdicts),
                "sample_assignment": sample,
            }
        )
    return {
        "schema": LESSONS_SCHEMA,
        "n_records": len(records),
        "n_lessons": len(lessons),
        "lessons": lessons,
    }


def distill_path(path: str | Path) -> dict[str, Any]:
    return distill(read_archive(path))
