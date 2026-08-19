from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal, Mapping

Sense = Literal["min", "max"]
VarKind = Literal["continuous", "integer", "binary"]
SolveStatus = Literal[
    "optimal",
    "feasible",
    "infeasible",
    "unbounded",
    "error",
    "unknown",
]
Verdict = Literal["agree", "disagree", "inconclusive", "error"]


@dataclass(frozen=True)
class Tolerances:
    """Numeric comparison policy. Specified up front to avoid false disagreements.

    For integer MILP with integer data, checks round to int when the
    assignment is within `integrality` of an integer, then compare exactly.
    Floating comparisons use max(abs, rel * scale).
    """

    primal_feasibility: float = 1e-6
    objective_abs: float = 1e-6
    objective_rel: float = 1e-6
    integrality: float = 1e-8

    def to_dict(self) -> dict[str, float]:
        return {
            "primal_feasibility": self.primal_feasibility,
            "objective_abs": self.objective_abs,
            "objective_rel": self.objective_rel,
            "integrality": self.integrality,
        }


@dataclass(frozen=True)
class ConstraintViolation:
    name: str
    violation: float
    detail: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "violation": float(self.violation),
            "detail": self.detail,
        }


@dataclass
class CheckResult:
    feasible: bool
    objective: float | None
    violations: list[ConstraintViolation] = field(default_factory=list)
    integrality_ok: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "feasible": bool(self.feasible),
            "objective": None if self.objective is None else float(self.objective),
            "violations": [v.to_dict() for v in self.violations],
            "integrality_ok": bool(self.integrality_ok),
        }


@dataclass
class SolveResult:
    solver: str
    status: SolveStatus
    assignment: dict[str, float]
    objective: float | None
    runtime_ms: float
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "solver": self.solver,
            "status": self.status,
            "assignment": {key: float(value) for key, value in self.assignment.items()},
            "objective": None if self.objective is None else float(self.objective),
            "runtime_ms": float(self.runtime_ms),
            "error": self.error,
        }


@dataclass
class ExchangeDirection:
    source: str
    target: str
    feasible: bool
    objective_source: float | None
    objective_in_target: float | None
    objective_match: bool | None
    violations: list[ConstraintViolation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        if not self.feasible:
            return False
        if self.objective_match is False:
            return False
        return True

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "target": self.target,
            "feasible": self.feasible,
            "objective_source": self.objective_source,
            "objective_in_target": self.objective_in_target,
            "objective_match": self.objective_match,
            "violations": [v.to_dict() for v in self.violations],
            "ok": self.ok,
        }


@dataclass
class ScoreVector:
    """Deterministic structured verdict. This is the evaluator-facing output."""

    problem_id: str
    verdict: Verdict
    verification_strength: str
    guarantee: str
    feasible: dict[str, bool]
    agreement: float
    objective: dict[str, float | None]
    optimality_status: dict[str, str]
    claimed_optima_match: bool | None
    counterexamples: list[dict[str, object]]
    runtime_ms: dict[str, float]
    tolerances: Tolerances
    notes: list[str] = field(default_factory=list)
    exchanges: list[ExchangeDirection] = field(default_factory=list)
    smt_feasible: dict[str, bool] = field(default_factory=dict)
    smt_objective_match: dict[str, bool | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "problem_id": self.problem_id,
            "verdict": self.verdict,
            "verification_strength": self.verification_strength,
            "guarantee": self.guarantee,
            "feasible": dict(self.feasible),
            "agreement": self.agreement,
            "objective": dict(self.objective),
            "optimality_status": dict(self.optimality_status),
            "claimed_optima_match": self.claimed_optima_match,
            "counterexamples": list(self.counterexamples),
            "runtime_ms": dict(self.runtime_ms),
            "tolerances": self.tolerances.to_dict(),
            "notes": list(self.notes),
            "exchanges": [e.to_dict() for e in self.exchanges],
            "smt_feasible": dict(self.smt_feasible),
            "smt_objective_match": dict(self.smt_objective_match),
        }


class Formulation(ABC):
    """One independently written solver encoding of a problem.

    Constraint bodies must not be imported from a shared IR. The only shared
    surface is the canonical variable names used to exchange solutions.
    """

    name: str
    variables: tuple[str, ...]
    sense: Sense
    problem_id: str = "unknown"

    @abstractmethod
    def solve(self) -> SolveResult:
        raise NotImplementedError

    @abstractmethod
    def check(
        self, assignment: Mapping[str, float], tol: Tolerances
    ) -> CheckResult:
        raise NotImplementedError


EXCHANGE_GUARANTEE = (
    "exchange-check only: each reported solution is feasible in the other "
    "formulation(s) and objective values match within tolerances. This is not "
    "a proof of global optimality, and correlated formulation bugs (the same "
    "mistake in every backend) are invisible at this layer."
)

SMT_GUARANTEE = (
    "SMT against the verification IR only. The reported assignment is feasible "
    "in the spec-derived Z3 encoding and the claimed objective matches the "
    "verification objective. Exchange check was not run."
)

EXCHANGE_SMT_GUARANTEE = (
    "exchange-check plus independent SMT of the verification IR: reported "
    "solutions are feasible in peer formulations and in the spec-derived Z3 "
    "encoding, and claimed objectives match the verification objective. This is "
    "not a dual/optimality certificate. The verification IR must not be used to "
    "generate solver code."
)
