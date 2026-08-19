"""Hypothesis / neighborhood properties over the verification IR.

These tests do not call solver formulations. Resource monotonicity perturbs
the spec RHS and re-solves the IR LP relaxation; formulations that hardcode
stock values are not re-solved.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Mapping

from hypothesis import HealthCheck, given, settings, strategies as st

from dubito.dual import lp_relaxation_objective
from dubito.ir import evaluate_witness
from dubito.numeric import numbers_close
from dubito.problem import (
    LinearConstraint,
    ProblemSpec,
    PropertySpec,
    VerificationIR,
    as_linear_ir,
)
from dubito.model import SolveResult, SolveStatus, Tolerances

_SOLVED: frozenset[SolveStatus] = frozenset({"optimal", "feasible"})
_EXHAUSTIVE_CAP = 81


@dataclass
class PropertyReport:
    ok: dict[str, bool | None] = field(default_factory=dict)
    counterexamples: list[dict[str, object]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": dict(self.ok),
            "counterexamples": list(self.counterexamples),
            "notes": list(self.notes),
        }


def check_properties(
    problem: ProblemSpec,
    *,
    solves: Mapping[str, SolveResult] | None = None,
    smt_feasible: Mapping[str, bool] | None = None,
    witness_feasible: Mapping[str, bool] | None = None,
) -> PropertyReport:
    spec = problem.properties
    report = PropertyReport()
    if spec is None:
        report.notes.append("no properties block")
        return report
    feasible = (
        dict(witness_feasible)
        if witness_feasible is not None
        else dict(smt_feasible or {})
    )
    if spec.local_optimality is not None:
        _run_local_optimality(
            problem,
            spec,
            report,
            solves=solves or {},
            witness_feasible=feasible,
        )
    if spec.resource_monotonicity is not None:
        _run_resource_monotonicity(problem, spec, report)
    return report


def _run_local_optimality(
    problem: ProblemSpec,
    spec: PropertySpec,
    report: PropertyReport,
    *,
    solves: Mapping[str, SolveResult],
    witness_feasible: Mapping[str, bool],
) -> None:
    local = spec.local_optimality
    assert local is not None
    if problem.verification is None:
        report.ok["local_optimality"] = None
        report.notes.append("local_optimality skipped: no verification IR")
        return
    integer_names = [
        name
        for name, var in problem.variables.items()
        if var.kind in {"integer", "binary"}
    ]
    continuous_names = [
        name
        for name, var in problem.variables.items()
        if var.kind == "continuous"
    ]
    candidates: list[tuple[str, dict[str, float], float]] = []
    for name, result in solves.items():
        if result.status not in _SOLVED or not result.assignment:
            continue
        if witness_feasible.get(name) is False:
            continue
        ir_check = evaluate_witness(problem, result.assignment, problem.tolerances)
        if ir_check is None or not ir_check.feasible or ir_check.objective is None:
            continue
        candidates.append((name, dict(result.assignment), float(ir_check.objective)))
    if not candidates:
        report.ok["local_optimality"] = None
        report.notes.append("local_optimality skipped: no IR-feasible candidate")
        return

    failed = False
    for name, assignment, claimed in candidates:
        if integer_names:
            neighbor = _better_neighbor(
                problem,
                assignment,
                claimed,
                integer_names,
                radius=max(1, int(local.radius)),
                max_examples=local.max_examples,
            )
        elif continuous_names:
            neighbor = _better_continuous_neighbor(
                problem,
                assignment,
                claimed,
                continuous_names,
                radius=float(local.radius),
                max_examples=local.max_examples,
            )
        else:
            neighbor = None
        if neighbor is not None:
            failed = True
            report.counterexamples.append(
                {
                    "kind": "local_optimality",
                    "solver": name,
                    "assignment": assignment,
                    "neighbor": neighbor["assignment"],
                    "claimed_objective": claimed,
                    "neighbor_objective": neighbor["objective"],
                }
            )
    report.ok["local_optimality"] = not failed
    if failed:
        report.notes.append("a nearby IR-feasible point improves the claimed objective")


def _better_neighbor(
    problem: ProblemSpec,
    assignment: Mapping[str, float],
    claimed: float,
    integer_names: list[str],
    *,
    radius: int,
    max_examples: int,
) -> dict[str, object] | None:
    size = (2 * radius + 1) ** len(integer_names)
    if size <= max(_EXHAUSTIVE_CAP, max_examples):
        return _exhaustive_better_neighbor(
            problem, assignment, claimed, integer_names, radius
        )
    return _hypothesis_better_neighbor(
        problem, assignment, claimed, integer_names, radius, max_examples
    )


def _exhaustive_better_neighbor(
    problem: ProblemSpec,
    assignment: Mapping[str, float],
    claimed: float,
    integer_names: list[str],
    radius: int,
) -> dict[str, object] | None:
    ranges = [range(-radius, radius + 1) for _ in integer_names]
    for deltas in itertools.product(*ranges):
        if all(delta == 0 for delta in deltas):
            continue
        neighbor = dict(assignment)
        for name, delta in zip(integer_names, deltas, strict=True):
            neighbor[name] = float(assignment[name] + delta)
        found = _neighbor_if_better(problem, claimed, neighbor)
        if found is not None:
            return found
    return None


def _hypothesis_better_neighbor(
    problem: ProblemSpec,
    assignment: Mapping[str, float],
    claimed: float,
    integer_names: list[str],
    radius: int,
    max_examples: int,
) -> dict[str, object] | None:
    found: dict[str, object] | None = None

    @settings(
        derandomize=True,
        database=None,
        max_examples=max_examples,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    )
    @given(
        deltas=st.fixed_dictionaries(
            {name: st.integers(-radius, radius) for name in integer_names}
        )
    )
    def _prop(deltas: dict[str, int]) -> None:
        nonlocal found
        if found is None and not all(delta == 0 for delta in deltas.values()):
            neighbor = dict(assignment)
            for name, delta in deltas.items():
                neighbor[name] = float(assignment[name] + delta)
            hit = _neighbor_if_better(problem, claimed, neighbor)
            if hit is not None:
                found = hit
        assert found is None

    try:
        _prop()
    except Exception:
        if found is None:
            raise
    return found


def _neighbor_if_better(
    problem: ProblemSpec, claimed: float, neighbor: Mapping[str, float]
) -> dict[str, object] | None:
    check = evaluate_witness(problem, neighbor, problem.tolerances)
    if check is None or not check.feasible or check.objective is None:
        return None
    if _strictly_better(problem.sense, float(check.objective), claimed, problem.tolerances):
        return {"assignment": dict(neighbor), "objective": float(check.objective)}
    return None


def _strictly_better(sense: str, new_obj: float, old_obj: float, tol: Tolerances) -> bool:
    if numbers_close(new_obj, old_obj, tol):
        return False
    if sense == "max":
        return new_obj > old_obj
    return new_obj < old_obj


def _better_continuous_neighbor(
    problem: ProblemSpec,
    assignment: Mapping[str, float],
    claimed: float,
    names: list[str],
    *,
    radius: float,
    max_examples: int,
) -> dict[str, object] | None:
    for offset in _continuous_stencil(names, radius):
        neighbor = _apply_continuous_offset(problem, assignment, offset)
        found = _neighbor_if_better(problem, claimed, neighbor)
        if found is not None:
            return found
    if 3 ** len(names) > _EXHAUSTIVE_CAP:
        return _hypothesis_continuous_neighbor(
            problem, assignment, claimed, names, radius, max_examples
        )
    remaining = max(0, max_examples - len(_continuous_stencil(names, radius)))
    if remaining == 0:
        return None
    return _hypothesis_continuous_neighbor(
        problem, assignment, claimed, names, radius, remaining
    )


def _continuous_stencil(names: list[str], radius: float) -> list[dict[str, float]]:
    if not names or radius <= 0:
        return []
    if 3 ** len(names) > _EXHAUSTIVE_CAP:
        return [{name: radius if index == 0 else 0.0} for index, name in enumerate(names)]
    coords = list(itertools.product((-1.0, 0.0, 1.0), repeat=len(names)))
    out: list[dict[str, float]] = []
    for scale in (radius, radius * 0.5):
        if scale <= 0:
            continue
        for coord in coords:
            if all(value == 0.0 for value in coord):
                continue
            out.append({name: scale * value for name, value in zip(names, coord, strict=True)})
    return out


def _apply_continuous_offset(
    problem: ProblemSpec, assignment: Mapping[str, float], offset: Mapping[str, float]
) -> dict[str, float]:
    neighbor = dict(assignment)
    for name, delta in offset.items():
        value = float(assignment[name]) + float(delta)
        spec = problem.variables[name]
        if spec.lower is not None:
            value = max(value, float(spec.lower))
        if spec.upper is not None:
            value = min(value, float(spec.upper))
        neighbor[name] = value
    return neighbor


def _hypothesis_continuous_neighbor(
    problem: ProblemSpec,
    assignment: Mapping[str, float],
    claimed: float,
    names: list[str],
    radius: float,
    max_examples: int,
) -> dict[str, object] | None:
    found: dict[str, object] | None = None

    @settings(
        derandomize=True,
        database=None,
        max_examples=max(1, max_examples),
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    )
    @given(
        deltas=st.fixed_dictionaries(
            {
                name: st.floats(
                    min_value=-radius,
                    max_value=radius,
                    allow_nan=False,
                    allow_infinity=False,
                    width=64,
                )
                for name in names
            }
        )
    )
    def _prop(deltas: dict[str, float]) -> None:
        nonlocal found
        if found is None and not all(abs(delta) <= 1e-15 for delta in deltas.values()):
            neighbor = _apply_continuous_offset(problem, assignment, deltas)
            hit = _neighbor_if_better(problem, claimed, neighbor)
            if hit is not None:
                found = hit
        assert found is None

    try:
        _prop()
    except Exception:
        if found is None:
            raise
    return found


def _run_resource_monotonicity(
    problem: ProblemSpec, spec: PropertySpec, report: PropertyReport
) -> None:
    mono = spec.resource_monotonicity
    assert mono is not None
    if as_linear_ir(problem) is None:
        report.ok["resource_monotonicity"] = None
        report.notes.append("resource_monotonicity skipped: no linear verification IR")
        return
    baseline = lp_relaxation_objective(problem)
    if baseline is None:
        report.ok["resource_monotonicity"] = None
        report.notes.append("resource_monotonicity skipped: LP relaxation did not solve")
        return

    found: dict[str, object] | None = None
    constraint_names = list(mono.constraints)

    @settings(
        derandomize=True,
        database=None,
        max_examples=mono.max_examples,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(
        bumps=st.fixed_dictionaries(
            {name: st.integers(0, mono.max_increase) for name in constraint_names}
        )
    )
    def _prop(bumps: dict[str, int]) -> None:
        nonlocal found
        if found is None and not all(value == 0 for value in bumps.values()):
            relaxed = _relax_resources(problem, bumps)
            new_opt = lp_relaxation_objective(relaxed)
            if new_opt is not None and _strictly_better(
                problem.sense, baseline, new_opt, problem.tolerances
            ):
                found = {
                    "kind": "resource_monotonicity",
                    "increases": dict(bumps),
                    "original_lp_opt": baseline,
                    "relaxed_lp_opt": new_opt,
                }
        assert found is None

    try:
        _prop()
    except Exception:
        if found is None:
            raise

    if found is not None:
        report.ok["resource_monotonicity"] = False
        report.counterexamples.append(found)
        report.notes.append(
            "verification IR failed resource monotonicity (spec bug, not formulation)"
        )
        return
    report.ok["resource_monotonicity"] = True


def _relax_resources(problem: ProblemSpec, bumps: Mapping[str, int]) -> ProblemSpec:
    ir = as_linear_ir(problem)
    assert ir is not None
    updated: list[LinearConstraint] = []
    for constraint in ir.constraints:
        delta = bumps.get(constraint.name, 0)
        if delta:
            updated.append(_relax_constraint(constraint, delta))
        else:
            updated.append(constraint)
    new_ir = VerificationIR(constraints=tuple(updated), objective=ir.objective)
    return replace(problem, verification=new_ir)


def _relax_constraint(constraint: LinearConstraint, delta: int) -> LinearConstraint:
    step = Fraction(delta)
    if constraint.op == "<=":
        return replace(constraint, rhs=constraint.rhs + step)
    if constraint.op == ">=":
        return replace(constraint, rhs=constraint.rhs - step)
    return constraint
