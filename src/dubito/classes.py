"""Problem-class verification profiles.

The router does not choose a solver and does not compile the verification IR
into CVXPY/OR-Tools/Pyomo. It chooses which verification layers may run, and
what the score is allowed to claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

LayerName = Literal[
    "code",
    "exchange",
    "smt",
    "dual",
    "residual",
    "properties",
    "kkt",
    "holdout",
    "dominance",
]
LayerStatus = str  # "ran" | "skipped:<reason>" | "off"

IMPLEMENTED_LAYERS: frozenset[str] = frozenset(
    {"code", "exchange", "smt", "dual", "residual", "properties"}
)

# YAML `class` values. Declared classes may load even when some layers are stubs.
PROBLEM_CLASSES: tuple[str, ...] = (
    "lp",
    "milp",
    "nlp",
    "convex",
    "sat",
    "blackbox",
    "symbolic_regression",
    "multiobjective",
    "routing",
)


@dataclass(frozen=True)
class ClassProfile:
    problem_class: str
    layers: tuple[str, ...]
    backends: tuple[str, ...]
    ceiling: str
    notes: str = ""


PROFILES: dict[str, ClassProfile] = {
    "lp": ClassProfile(
        problem_class="lp",
        layers=("code", "exchange", "smt", "dual", "properties"),
        backends=("cvxpy", "ortools", "scipy", "pyomo"),
        ceiling="LP dual certificate when the bound closes; not a solver-generated proof",
    ),
    "milp": ClassProfile(
        problem_class="milp",
        layers=("code", "exchange", "smt", "dual", "properties"),
        backends=("cvxpy", "ortools", "pyomo"),
        ceiling=(
            "integer-feasible point matching the LP dual is IP-optimal against this IR; "
            "a remaining gap is not a MILP certificate"
        ),
    ),
    "nlp": ClassProfile(
        problem_class="nlp",
        layers=("code", "exchange", "residual", "properties"),
        backends=("scipy", "cvxpy", "pyomo"),
        ceiling="residual feasibility and local neighborhood only; not a global certificate",
        notes="nonlinear real SMT is incomplete; P3a does not run Z3 on residual IR",
    ),
    "convex": ClassProfile(
        problem_class="convex",
        layers=("code", "exchange", "residual", "kkt", "properties"),
        backends=("cvxpy", "scipy"),
        ceiling="KKT/dual gap when implemented; until then residual only",
        notes="kkt layer is not implemented",
    ),
    "sat": ClassProfile(
        problem_class="sat",
        layers=("code", "exchange", "smt"),
        backends=("ortools", "z3"),
        ceiling="peer encodings are equals; no LP dual",
        notes="sat exchange/SMT pairing is not implemented",
    ),
    "blackbox": ClassProfile(
        problem_class="blackbox",
        layers=("code", "properties"),
        backends=("optuna", "scipy"),
        ceiling="property tests only; claimed optima are not certificates",
        notes="Optuna extra is reserved; no black-box backend ships in P3a",
    ),
    "symbolic_regression": ClassProfile(
        problem_class="symbolic_regression",
        layers=("code", "holdout", "properties"),
        backends=("pysr",),
        ceiling="holdout plus properties; not an identity proof",
        notes="holdout layer is not implemented",
    ),
    "multiobjective": ClassProfile(
        problem_class="multiobjective",
        layers=("code", "dominance"),
        backends=("pymoo", "optuna"),
        ceiling="Pareto coverage when implemented",
        notes="dominance layer is not implemented",
    ),
    "routing": ClassProfile(
        problem_class="routing",
        layers=("code", "exchange"),
        backends=("ortools",),
        ceiling="exchange against a peer formulation only",
        notes="routing-specific exchange is not implemented beyond generic exchange",
    ),
}


@dataclass
class RoutedLayers:
    profile: ClassProfile
    planned: tuple[str, ...]
    status: dict[str, str] = field(default_factory=dict)

    def allows(self, layer: str) -> bool:
        """True when the layer is still scheduled to run."""

        return self.status.get(layer) == "pending"

    def mark_ran(self, layer: str) -> None:
        self.status[layer] = "ran"

    def mark_skipped(self, layer: str, reason: str) -> None:
        self.status[layer] = f"skipped:{reason}"

    def mark_off(self, layer: str) -> None:
        self.status[layer] = "off"

    def strength(self) -> str:
        ran = [name for name in self.planned if self.status.get(name) == "ran"]
        extra = [
            name
            for name, state in self.status.items()
            if state == "ran" and name not in ran
        ]
        ordered = [*ran, *extra]
        return "+".join(ordered) if ordered else "none"

    def to_dict(self) -> dict[str, object]:
        return {
            "class": self.profile.problem_class,
            "ceiling": self.profile.ceiling,
            "backends": list(self.profile.backends),
            "planned": list(self.planned),
            "status": dict(self.status),
            "strength": self.strength(),
            "notes": self.profile.notes,
        }
