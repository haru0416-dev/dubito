from __future__ import annotations

import json

from dubito.model import ScoreVector


def score_to_dict(score: ScoreVector) -> dict[str, object]:
    return score.to_dict()


def score_to_json(score: ScoreVector, *, indent: int | None = 2) -> str:
    return json.dumps(score.to_dict(), indent=indent, sort_keys=True, default=_json_default)


def _json_default(value: object) -> object:
    if isinstance(value, float):
        return value
    raise TypeError(f"not JSON serializable: {type(value)!r}")
