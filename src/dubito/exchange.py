from __future__ import annotations

from dubito.numeric import numbers_close
from dubito.model import (
    EXCHANGE_GUARANTEE,
    ExchangeDirection,
    Formulation,
    ScoreVector,
    SolveResult,
    SolveStatus,
    Tolerances,
    Verdict,
)

_SOLVED: frozenset[SolveStatus] = frozenset({"optimal", "feasible"})


def exchange_check(
    formulations: list[Formulation],
    *,
    tol: Tolerances | None = None,
    problem_id: str | None = None,
    solves: dict[str, SolveResult] | None = None,
) -> ScoreVector:
    """Substitute each solver's solution into every other formulation.

    Also compares claimed objective values when both statuses are solved.
    Disagreement in either channel is a formulation-bug signal.
    """

    if len(formulations) < 2:
        raise ValueError("exchange_check requires at least two formulations")
    tol = tol or Tolerances()
    pid = problem_id or formulations[0].problem_id

    notes: list[str] = []
    if solves is None:
        solves = {form.name: form.solve() for form in formulations}
    else:
        solves = dict(solves)
        for form in formulations:
            if form.name not in solves:
                solves[form.name] = form.solve()
    for form in formulations:
        result = solves[form.name]
        if result.error:
            notes.append(f"{form.name} error: {result.error}")

    exchanges: list[ExchangeDirection] = []
    counterexamples: list[dict[str, object]] = []

    by_name = {form.name: form for form in formulations}
    for source in formulations:
        src = solves[source.name]
        if src.status not in _SOLVED or not src.assignment:
            continue
        for target in formulations:
            if target.name == source.name:
                continue
            check = target.check(src.assignment, tol)
            obj_match: bool | None
            if src.objective is None or check.objective is None:
                obj_match = None
            else:
                obj_match = numbers_close(src.objective, check.objective, tol)
            direction = ExchangeDirection(
                source=source.name,
                target=target.name,
                feasible=check.feasible and check.integrality_ok,
                objective_source=src.objective,
                objective_in_target=check.objective,
                objective_match=obj_match,
                violations=list(check.violations),
            )
            exchanges.append(direction)
            if not direction.ok:
                counterexamples.append(
                    {
                        "kind": (
                            "infeasible"
                            if not direction.feasible
                            else "objective_mismatch"
                        ),
                        "assignment": dict(src.assignment),
                        "direction": direction.to_dict(),
                    }
                )

    feasible = {
        name: solves[name].status in _SOLVED and bool(solves[name].assignment)
        for name in by_name
    }
    objective = {name: solves[name].objective for name in by_name}
    optimality_status = {name: solves[name].status for name in by_name}
    runtime_ms = {name: solves[name].runtime_ms for name in by_name}

    solved_names = [
        name for name, status in optimality_status.items() if status in _SOLVED
    ]
    claimed_optima_match: bool | None
    if len(solved_names) < 2:
        claimed_optima_match = None
    else:
        claimed_optima_match = all(
            numbers_close(
                solves[solved_names[0]].objective, solves[name].objective, tol
            )
            for name in solved_names[1:]
        )
        if claimed_optima_match is False:
            counterexamples.append(
                {
                    "kind": "claimed_optima_mismatch",
                    "objectives": {n: solves[n].objective for n in solved_names},
                    "statuses": {n: solves[n].status for n in solved_names},
                }
            )

    if exchanges:
        agreement = sum(1.0 for ex in exchanges if ex.ok) / len(exchanges)
    else:
        agreement = 0.0
        notes.append("no exchange directions: fewer than two solved assignments")

    statuses = {solves[n].status for n in by_name}
    verdict: Verdict
    if any(solves[n].status == "error" for n in by_name):
        verdict = "error"
    elif "infeasible" in statuses and _SOLVED & statuses:
        verdict = "disagree"
        notes.append("one backend reports infeasible while another reports a solution")
    elif not exchanges and len(solved_names) < 2:
        verdict = "inconclusive"
    elif agreement < 1.0 or claimed_optima_match is False:
        verdict = "disagree"
    elif agreement == 1.0 and claimed_optima_match is not False:
        verdict = "agree"
    else:
        verdict = "inconclusive"

    return ScoreVector(
        problem_id=pid,
        verdict=verdict,
        verification_strength="exchange",
        guarantee=EXCHANGE_GUARANTEE,
        feasible=feasible,
        agreement=agreement,
        objective=objective,
        optimality_status=optimality_status,
        claimed_optima_match=claimed_optima_match,
        counterexamples=counterexamples,
        runtime_ms=runtime_ms,
        tolerances=tol,
        notes=notes,
        exchanges=exchanges,
    )
