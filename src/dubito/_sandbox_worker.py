from __future__ import annotations

import json
import sys

from dubito.load import load_formulation_here
from dubito.model import Tolerances


def main() -> int:
    message = json.loads(sys.stdin.read())
    form = load_formulation_here(message["path"])
    if message["op"] == "meta":
        json.dump(
            {
                "name": form.name,
                "variables": list(form.variables),
                "sense": form.sense,
                "problem_id": form.problem_id,
            },
            sys.stdout,
        )
        return 0
    if message["op"] == "solve":
        json.dump(form.solve().to_dict(), sys.stdout)
        return 0
    if message["op"] == "check":
        tol = Tolerances(**message["tolerances"])
        json.dump(form.check(message["assignment"], tol).to_dict(), sys.stdout)
        return 0
    raise SystemExit(f"unknown op {message['op']}")


if __name__ == "__main__":
    raise SystemExit(main())
