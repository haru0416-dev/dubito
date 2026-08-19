"""LP dual / relaxation bound from the verification IR only.

Solver formulations must not import this module. The dual is a witness against
the spec, not a compilation of CVXPY or OR-Tools models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np
from scipy.optimize import linprog

from dubito.numeric import numbers_close
from dubito.problem import ProblemSpec, VerificationIR

_LINPROG_OPTS = {"disp": False}


@dataclass
class DualReport:
    """Dual / LP-relaxation bound compared to claimed objectives."""

    bound: float | None
    status: str
    gap: dict[str, float | None] = field(default_factory=dict)
    closed: dict[str, bool | None] = field(default_factory=dict)
    exceeded: dict[str, bool] = field(default_factory=dict)
    complementary_slackness: dict[str, bool | None] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    dual_assignment: dict[str, float] | None = None
    lp_relaxation: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "bound": self.bound,
            "status": self.status,
            "gap": dict(self.gap),
            "closed": dict(self.closed),
            "exceeded": dict(self.exceeded),
            "complementary_slackness": dict(self.complementary_slackness),
            "notes": list(self.notes),
            "dual_assignment": self.dual_assignment,
            "lp_relaxation": self.lp_relaxation,
        }


def check_dual(
    problem: ProblemSpec,
    claimed: Mapping[str, float | None],
    *,
    assignments: Mapping[str, Mapping[str, float]] | None = None,
) -> DualReport:
    """Compare claimed objectives to the verification-IR dual bound.

    For a max problem the dual is an upper bound; a claimed value strictly
    above it is impossible. A gap below the bound is allowed for MILP
    (LP-relaxation only). For min, the dual is a lower bound.
    """

    if problem.verification is None:
        return DualReport(bound=None, status="skipped", notes=["no verification IR"])

    lp_opt, lp_status, lp_notes = _solve_lp_relaxation(problem)
    dual_opt, dual_status, dual_y, dual_notes = _solve_dual(problem)

    notes = [*lp_notes, *dual_notes]
    bound: float | None = None
    status = "error"

    if dual_status == "optimal" and dual_opt is not None:
        bound = dual_opt
        status = "optimal"
        if lp_opt is not None and not numbers_close(lp_opt, dual_opt, problem.tolerances):
            notes.append(
                f"LP relaxation {lp_opt} and dual {dual_opt} differ; using dual bound"
            )
    elif lp_status == "optimal" and lp_opt is not None:
        bound = lp_opt
        status = "optimal"
        notes.append("dual solve did not succeed; using LP-relaxation objective as bound")
    elif dual_status == "unbounded" or lp_status == "infeasible":
        status = "primal_infeasible"
        notes.append("verification-IR LP relaxation appears infeasible")
    elif dual_status == "infeasible" or lp_status == "unbounded":
        status = "unbounded"
        notes.append("verification-IR LP relaxation appears unbounded")
    else:
        status = dual_status if dual_status != "error" else lp_status
        notes.append("could not compute a dual / LP-relaxation bound")

    report = DualReport(
        bound=bound,
        status=status,
        notes=notes,
        dual_assignment=dual_y,
        lp_relaxation=lp_opt,
    )
    assignments = assignments or {}
    for name, obj in claimed.items():
        if bound is None or obj is None:
            report.gap[name] = None
            report.closed[name] = None
            report.exceeded[name] = False
            continue
        gap = _signed_gap(problem.sense, bound, obj)
        report.gap[name] = gap
        report.closed[name] = numbers_close(bound, obj, problem.tolerances)
        # Negative gap (beyond tolerance) means the claim beats the bound.
        report.exceeded[name] = gap < -max(
            problem.tolerances.objective_abs,
            problem.tolerances.objective_rel * max(1.0, abs(bound), abs(obj)),
        )
        assignment = assignments.get(name)
        if assignment is not None and dual_y is not None:
            report.complementary_slackness[name] = _complementary_slackness(
                problem, assignment, dual_y, problem.tolerances.primal_feasibility
            )
        else:
            report.complementary_slackness[name] = None
    return report


def lp_relaxation_objective(problem: ProblemSpec) -> float | None:
    opt, status, _ = _solve_lp_relaxation(problem)
    if status != "optimal":
        return None
    return opt


def _signed_gap(sense: str, bound: float, claimed: float) -> float:
    """Non-negative when the claim respects the bound (max: bound - claimed)."""

    if sense == "max":
        return bound - claimed
    return claimed - bound


def _solve_lp_relaxation(
    problem: ProblemSpec,
) -> tuple[float | None, str, list[str]]:
    ir = _require_ir(problem)
    names = list(problem.variables)
    A, b, _ = _constraint_rows(ir, names)
    c = np.array([float(ir.objective.get(name, 0)) for name in names], dtype=float)
    c_lp = -c if problem.sense == "max" else c
    bounds = [
        (
            None if spec.lower is None else float(spec.lower),
            None if spec.upper is None else float(spec.upper),
        )
        for spec in problem.variables.values()
    ]
    kwargs: dict[str, object] = {
        "c": c_lp,
        "bounds": bounds,
        "method": "highs",
        "options": _LINPROG_OPTS,
    }
    if A.size:
        kwargs["A_ub"] = A
        kwargs["b_ub"] = b
    result = linprog(**kwargs)
    return _linprog_objective(result, problem.sense, negate_max=True)


def _solve_dual(
    problem: ProblemSpec,
) -> tuple[float | None, str, dict[str, float] | None, list[str]]:
    """Dual of the standardized max form: min b'y s.t. A^T y = c, y >= 0.

    Bounds are folded into Ax <= b so every x is treated as free.
    """

    ir = _require_ir(problem)
    names = list(problem.variables)
    A, b, row_names = _standard_max_rows(problem, ir, names)
    if A.size == 0:
        return None, "skipped", None, ["no dual rows"]
    c = np.array([float(ir.objective.get(name, 0)) for name in names], dtype=float)
    c_max = c if problem.sense == "max" else -c
    result = linprog(
        c=b,
        A_eq=A.T,
        b_eq=c_max,
        bounds=(0, None),
        method="highs",
        options=_LINPROG_OPTS,
    )
    opt, status, notes = _linprog_objective(result, "min", negate_max=False)
    if status != "optimal" or opt is None or result.x is None:
        return opt, status, None, notes
    dual_obj = float(opt) if problem.sense == "max" else -float(opt)
    assignment = {
        row_names[i]: float(result.x[i]) for i in range(len(row_names))
    }
    return dual_obj, "optimal", assignment, notes


def _linprog_objective(
    result: object, sense: str, *, negate_max: bool
) -> tuple[float | None, str, list[str]]:
    success = bool(getattr(result, "success", False))
    message = str(getattr(result, "message", "") or "")
    fun = getattr(result, "fun", None)
    status_code = int(getattr(result, "status", -1))
    # scipy: 0 ok, 1 iter/time, 2 infeasible, 3 unbounded, 4 numerical
    if success and fun is not None:
        value = float(fun)
        if negate_max and sense == "max":
            value = -value
        return value, "optimal", []
    if status_code == 2:
        return None, "infeasible", [message]
    if status_code == 3:
        return None, "unbounded", [message]
    return None, "error", [message or "linprog failed"]


def _constraint_rows(
    ir: VerificationIR, names: list[str]
) -> tuple[np.ndarray, np.ndarray, tuple[str, ...]]:
    rows: list[list[float]] = []
    rhs: list[float] = []
    row_names: list[str] = []
    for constraint in ir.constraints:
        vec = [float(constraint.terms.get(name, 0)) for name in names]
        if constraint.op == "<=":
            rows.append(vec)
            rhs.append(float(constraint.rhs))
            row_names.append(constraint.name)
        elif constraint.op == ">=":
            rows.append([-value for value in vec])
            rhs.append(-float(constraint.rhs))
            row_names.append(constraint.name)
        else:
            rows.append(vec)
            rhs.append(float(constraint.rhs))
            row_names.append(f"{constraint.name}:eq+")
            rows.append([-value for value in vec])
            rhs.append(-float(constraint.rhs))
            row_names.append(f"{constraint.name}:eq-")
    if not rows:
        return np.zeros((0, len(names))), np.zeros(0), ()
    return np.array(rows, dtype=float), np.array(rhs, dtype=float), tuple(row_names)


def _standard_max_rows(
    problem: ProblemSpec, ir: VerificationIR, names: list[str]
) -> tuple[np.ndarray, np.ndarray, tuple[str, ...]]:
    A, b, row_names = _constraint_rows(ir, names)
    extra_rows: list[np.ndarray] = []
    extra_b: list[float] = []
    extra_names: list[str] = []
    n = len(names)
    for index, spec in enumerate(problem.variables.values()):
        if spec.upper is not None:
            row = np.zeros(n)
            row[index] = 1.0
            extra_rows.append(row)
            extra_b.append(float(spec.upper))
            extra_names.append(f"bound_hi:{spec.name}")
        if spec.lower is not None:
            row = np.zeros(n)
            row[index] = -1.0
            extra_rows.append(row)
            extra_b.append(-float(spec.lower))
            extra_names.append(f"bound_lo:{spec.name}")
    if extra_rows:
        extra_a = np.vstack(extra_rows)
        A = extra_a if A.size == 0 else np.vstack([A, extra_a])
        b = np.concatenate([b, np.array(extra_b, dtype=float)])
        row_names = tuple(list(row_names) + extra_names)
    return A, b, row_names


def _complementary_slackness(
    problem: ProblemSpec,
    assignment: Mapping[str, float],
    dual_y: Mapping[str, float],
    tol: float,
) -> bool:
    ir = _require_ir(problem)
    names = list(problem.variables)
    A, b, row_names = _standard_max_rows(problem, ir, names)
    x = np.array([float(assignment.get(name, 0.0)) for name in names], dtype=float)
    y = np.array([float(dual_y.get(name, 0.0)) for name in row_names], dtype=float)
    slack = b - A @ x
    return bool(np.all(np.abs(y * slack) <= max(tol, 1e-6)))


def _require_ir(problem: ProblemSpec) -> VerificationIR:
    if problem.verification is None:
        raise ValueError(f"problem {problem.id} has no verification IR")
    return problem.verification
