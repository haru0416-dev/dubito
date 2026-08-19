from __future__ import annotations

from pathlib import Path

from dubito.archive import append_counterexamples
from dubito.dual import DualReport, check_dual
from dubito.exchange import exchange_check
from dubito.model import (
    DUAL_CLOSED_LP_GUARANTEE,
    DUAL_CLOSED_MILP_GUARANTEE,
    DUAL_GAP_GUARANTEE,
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
from dubito.properties import PropertyReport, check_properties
from dubito.residual import evaluate_residual
from dubito.router import RoutedLayers, layer_pending, route
from dubito.z3check import LinearZ3Spec

_SOLVED: frozenset[SolveStatus] = frozenset({"optimal", "feasible"})


def verify(
    formulations: list[Formulation],
    problem: ProblemSpec,
    *,
    solves: dict[str, SolveResult] | None = None,
    check_dual: bool = True,
    check_properties: bool = True,
    archive_path: str | Path | None = None,
) -> ScoreVector:
    """Run the class router, then each pending verification layer."""

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

    routed = route(
        problem,
        check_dual=check_dual,
        check_properties=check_properties,
        n_formulations=len(formulations),
    )

    if layer_pending(routed, "exchange"):
        score = exchange_check(
            formulations,
            tol=problem.tolerances,
            problem_id=problem.id,
            solves=solves,
        )
        routed.mark_ran("exchange")
    elif len(formulations) >= 2:
        score = exchange_check(
            formulations,
            tol=problem.tolerances,
            problem_id=problem.id,
            solves=solves,
        )
        score.notes.append(
            f"exchange ran outside profile ({problem.problem_class}); treating as extra signal"
        )
        routed.mark_ran("exchange")
    else:
        score = _single_formulation_score(formulations[0], solves[formulations[0].name], problem)

    _annotate_interface(score, formulations, problem)

    if layer_pending(routed, "smt"):
        _attach_smt(score, solves, problem)
        routed.mark_ran("smt")
    if layer_pending(routed, "residual"):
        _attach_residual(score, solves, problem)
        routed.mark_ran("residual")
    dual_report: DualReport | None = None
    if layer_pending(routed, "dual"):
        dual_report = _attach_dual(score, solves, problem)
        routed.mark_ran("dual")
    prop_report: PropertyReport | None = None
    if layer_pending(routed, "properties"):
        witness = score.smt_feasible or score.residual_feasible
        prop_report = _attach_properties(score, solves, problem, witness_feasible=witness)
        routed.mark_ran("properties")

    for layer, state in routed.status.items():
        if state.startswith("skipped:") or state == "off":
            score.notes.append(f"layer {layer}: {state}")

    score.layers = dict(routed.status)
    score.profile = routed.to_dict()
    score.verification_strength = routed.strength()
    _refresh_guarantee(
        score, problem, dual_report=dual_report, prop_report=prop_report, routed=routed
    )

    if archive_path is not None:
        append_counterexamples(
            archive_path,
            score,
            problem,
            [form.name for form in formulations],
        )
    return score


def _single_formulation_score(
    form: Formulation, solved: SolveResult, problem: ProblemSpec
) -> ScoreVector:
    feasible = solved.status in _SOLVED and bool(solved.assignment)
    return ScoreVector(
        problem_id=problem.id,
        verdict="inconclusive",
        verification_strength="none",
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
        score.guarantee = EXCHANGE_SMT_GUARANTEE
    else:
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


def _attach_dual(
    score: ScoreVector, solves: dict[str, SolveResult], problem: ProblemSpec
) -> DualReport:
    claimed = {name: result.objective for name, result in solves.items()}
    assignments = {
        name: dict(result.assignment)
        for name, result in solves.items()
        if result.status in _SOLVED and result.assignment
    }
    report = check_dual(problem, claimed, assignments=assignments)
    score.dual_bound = report.bound
    score.dual_gap = dict(report.gap)
    score.dual_closed = dict(report.closed)
    score.notes.extend(report.notes)
    for name, exceeded in report.exceeded.items():
        if not exceeded:
            continue
        score.counterexamples.append(
            {
                "kind": "dual_bound_exceeded",
                "solver": name,
                "claimed": claimed.get(name),
                "dual_bound": report.bound,
                "assignment": assignments.get(name, {}),
            }
        )
        score.notes.append(
            f"{name} claimed objective exceeds the verification-IR dual bound"
        )
        _downgrade(score, "disagree")
    return report


def _attach_residual(
    score: ScoreVector, solves: dict[str, SolveResult], problem: ProblemSpec
) -> None:
    residual_feasible: dict[str, bool] = {}
    residual_objective_match: dict[str, bool | None] = {}
    for name, result in solves.items():
        if result.status not in _SOLVED or not result.assignment:
            residual_feasible[name] = False
            residual_objective_match[name] = None
            continue
        check = evaluate_residual(problem, result.assignment, problem.tolerances)
        obj_match: bool | None
        if result.objective is None or check.objective is None:
            obj_match = None
        else:
            obj_match = numbers_close(result.objective, check.objective, problem.tolerances)
        residual_feasible[name] = bool(check.feasible and check.integrality_ok)
        residual_objective_match[name] = obj_match
        if not residual_feasible[name]:
            score.counterexamples.append(
                {
                    "kind": "residual_infeasible",
                    "solver": name,
                    "assignment": dict(result.assignment),
                    "violations": [item.to_dict() for item in check.violations],
                }
            )
        elif obj_match is False:
            score.counterexamples.append(
                {
                    "kind": "residual_objective_mismatch",
                    "solver": name,
                    "assignment": dict(result.assignment),
                    "claimed": result.objective,
                    "verification_objective": check.objective,
                }
            )
    score.residual_feasible = residual_feasible
    score.residual_objective_match = residual_objective_match
    residual_ok = bool(residual_feasible) and all(residual_feasible.values()) and all(
        match is not False for match in residual_objective_match.values()
    )
    if not residual_ok:
        if score.verdict == "agree":
            score.notes.append("solvers agree with each other but not with the residual IR")
        _downgrade(score, "disagree")
    elif not score.exchanges:
        if all(solves[name].status in _SOLVED for name in residual_feasible) and residual_ok:
            score.verdict = "agree"


def _attach_properties(
    score: ScoreVector,
    solves: dict[str, SolveResult],
    problem: ProblemSpec,
    *,
    witness_feasible: dict[str, bool] | None = None,
) -> PropertyReport:
    report = check_properties(
        problem, solves=solves, witness_feasible=witness_feasible or score.smt_feasible
    )
    score.properties_ok = dict(report.ok)
    score.notes.extend(report.notes)
    score.counterexamples.extend(report.counterexamples)
    if any(value is False for value in report.ok.values()) or report.counterexamples:
        _downgrade(score, "disagree")
    return report


def _refresh_guarantee(
    score: ScoreVector,
    problem: ProblemSpec,
    *,
    dual_report: DualReport | None,
    prop_report: PropertyReport | None,
    routed: RoutedLayers,
) -> None:
    if dual_report is None or dual_report.bound is None:
        score.guarantee = (
            f"{routed.profile.ceiling}. The verification IR must not be used to generate solver code."
        )
        if prop_report is not None and all(value is not False for value in prop_report.ok.values()):
            score.guarantee = score.guarantee.rstrip(".") + "; Hypothesis properties passed."
        return
    closed = [value for value in dual_report.closed.values() if value is not None]
    any_exceeded = any(dual_report.exceeded.values())
    if closed and all(closed) and not any_exceeded:
        if problem.problem_class == "milp":
            score.guarantee = DUAL_CLOSED_MILP_GUARANTEE
        else:
            score.guarantee = DUAL_CLOSED_LP_GUARANTEE
    elif not any_exceeded:
        score.guarantee = DUAL_GAP_GUARANTEE
    if prop_report is not None and all(value is not False for value in prop_report.ok.values()):
        if "Hypothesis properties" not in score.guarantee:
            score.guarantee = score.guarantee.rstrip(".") + "; Hypothesis properties passed."


def _downgrade(score: ScoreVector, verdict: Verdict) -> None:
    if score.verdict == "error":
        return
    score.verdict = verdict
