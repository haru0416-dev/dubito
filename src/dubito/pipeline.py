from __future__ import annotations

from dubito.exchange import exchange_check
from dubito.model import (
    EXCHANGE_SMT_GUARANTEE,
    SMT_GUARANTEE,
    Formulation,
    ScoreVector,
    SolveResult,
    SolveStatus,
    Verdict,
)
from dubito.numeric import numbers_close
from dubito.problem import ProblemSpec
from dubito.z3check import LinearZ3Spec

_SOLVED: frozenset[SolveStatus] = frozenset({"optimal", "feasible"})


def verify(
    formulations: list[Formulation],
    problem: ProblemSpec,
    *,
    solves: dict[str, SolveResult] | None = None,
) -> ScoreVector:
    """Run exchange check (if 2+ formulations) then SMT against the verification IR."""

    if not formulations:
        raise ValueError("verify requires at least one formulation")
    names = [form.name for form in formulations]
    if len(names) != len(set(names)):
        raise ValueError(f"formulation names must be unique, got {names}")

    if solves is None:
        solves = {form.name: form.solve() for form in formulations}
    else:
        solves = dict(solves)
        for form in formulations:
            if form.name not in solves:
                solves[form.name] = form.solve()

    if len(formulations) >= 2:
        score = exchange_check(
            formulations,
            tol=problem.tolerances,
            problem_id=problem.id,
            solves=solves,
        )
    else:
        score = _single_formulation_score(formulations[0], solves[formulations[0].name], problem)

    _annotate_interface(score, formulations, problem)

    if problem.verification is None:
        if any("variables" in note or "sense" in note for note in score.notes) and score.verdict == "agree":
            score.verdict = "disagree"
        return score

    _attach_smt(score, solves, problem)
    return score


def _single_formulation_score(
    form: Formulation, solved: SolveResult, problem: ProblemSpec
) -> ScoreVector:
    feasible = solved.status in _SOLVED and bool(solved.assignment)
    return ScoreVector(
        problem_id=problem.id,
        verdict="inconclusive",
        verification_strength="smt",
        guarantee=SMT_GUARANTEE,
        feasible={form.name: feasible},
        agreement=1.0,
        objective={form.name: solved.objective},
        optimality_status={form.name: solved.status},
        claimed_optima_match=None,
        counterexamples=[],
        runtime_ms={form.name: solved.runtime_ms},
        tolerances=problem.tolerances,
        notes=["single formulation: exchange check skipped"],
    )


def _annotate_interface(
    score: ScoreVector, formulations: list[Formulation], problem: ProblemSpec
) -> None:
    expected = set(problem.variables)
    for form in formulations:
        if set(form.variables) != expected:
            score.notes.append(
                f"{form.name} variables {form.variables} do not match spec {tuple(problem.variables)}"
            )
            if score.verdict != "error":
                score.verdict = "disagree"
        if form.sense != problem.sense:
            score.notes.append(f"{form.name} sense {form.sense!r} does not match spec {problem.sense!r}")
            if score.verdict != "error":
                score.verdict = "disagree"


def _attach_smt(
    score: ScoreVector, solves: dict[str, SolveResult], problem: ProblemSpec
) -> None:
    spec = LinearZ3Spec(problem)
    smt_feasible: dict[str, bool] = {}
    smt_objective_match: dict[str, bool | None] = {}
    for name, result in solves.items():
        if result.status not in _SOLVED or not result.assignment:
            smt_feasible[name] = False
            smt_objective_match[name] = None
            continue
        check = spec.check_assignment(result.assignment, problem.tolerances)
        obj_match: bool | None
        if result.objective is None or check.objective is None:
            obj_match = None
        else:
            obj_match = numbers_close(result.objective, check.objective, problem.tolerances)
        smt_feasible[name] = bool(check.feasible and check.integrality_ok)
        smt_objective_match[name] = obj_match
        if not smt_feasible[name]:
            score.counterexamples.append(
                {
                    "kind": "smt_infeasible",
                    "solver": name,
                    "assignment": dict(result.assignment),
                    "violations": [item.to_dict() for item in check.violations],
                }
            )
        elif obj_match is False:
            score.counterexamples.append(
                {
                    "kind": "smt_objective_mismatch",
                    "solver": name,
                    "assignment": dict(result.assignment),
                    "claimed": result.objective,
                    "verification_objective": check.objective,
                }
            )
    score.smt_feasible = smt_feasible
    score.smt_objective_match = smt_objective_match
    if score.exchanges:
        score.verification_strength = "exchange+smt"
        score.guarantee = EXCHANGE_SMT_GUARANTEE
    else:
        score.verification_strength = "smt"
        score.guarantee = SMT_GUARANTEE

    smt_ok = bool(smt_feasible) and all(smt_feasible.values()) and all(
        match is not False for match in smt_objective_match.values()
    )
    if not smt_ok:
        if score.verdict == "agree":
            score.notes.append("solvers agree with each other but not with the verification IR")
        _downgrade(score, "disagree")
    elif not score.exchanges:
        if all(solves[name].status in _SOLVED for name in smt_feasible) and smt_ok:
            score.verdict = "agree"


def _downgrade(score: ScoreVector, verdict: Verdict) -> None:
    if score.verdict == "error":
        return
    score.verdict = verdict
