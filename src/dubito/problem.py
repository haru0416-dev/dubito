from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal, Mapping

import yaml

from dubito.model import Sense, Tolerances, VarKind

SCHEMA_V1 = "dubito.problem/v1"
SUPPORTED_CLASSES = frozenset({"lp", "milp"})
ConstraintOp = Literal["<=", ">=", "=="]


class ProblemSpecError(ValueError):
    """Raised when a problem YAML file does not match the Phase 1 schema."""


@dataclass(frozen=True)
class VariableSpec:
    name: str
    kind: VarKind
    lower: Fraction | None = None
    upper: Fraction | None = None


@dataclass(frozen=True)
class LinearConstraint:
    name: str
    terms: dict[str, Fraction]
    op: ConstraintOp
    rhs: Fraction


@dataclass(frozen=True)
class VerificationIR:
    """Linear constraint set for the verification layer only.

    Solver formulations must not import or compile this block. It exists so
    Z3 can be rebuilt from the spec on a path separate from CVXPY/OR-Tools.
    """

    constraints: tuple[LinearConstraint, ...]
    objective: dict[str, Fraction]


@dataclass(frozen=True)
class ProblemSpec:
    id: str
    problem_class: Literal["lp", "milp"]
    sense: Sense
    variables: dict[str, VariableSpec]
    narrative: str
    tolerances: Tolerances
    verification: VerificationIR | None
    schema: str = SCHEMA_V1
    source: str | None = None

    @property
    def variable_names(self) -> tuple[str, ...]:
        return tuple(self.variables)


def load_problem(path: str | Path) -> ProblemSpec:
    file_path = Path(path).resolve()
    raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ProblemSpecError(f"{file_path} must contain a YAML mapping")
    return parse_problem(raw, source=str(file_path))


def parse_problem(raw: Mapping[str, Any], *, source: str | None = None) -> ProblemSpec:
    schema = str(raw.get("schema", SCHEMA_V1))
    if schema != SCHEMA_V1:
        raise ProblemSpecError(f"unsupported schema {schema!r}; expected {SCHEMA_V1}")
    problem_id = _require_str(raw, "id")
    problem_class = _require_str(raw, "class")
    if problem_class not in SUPPORTED_CLASSES:
        raise ProblemSpecError(
            f"class {problem_class!r} is not a Phase 1 class; supported: {sorted(SUPPORTED_CLASSES)}"
        )
    sense = _require_str(raw, "sense")
    if sense not in {"min", "max"}:
        raise ProblemSpecError(f"sense must be min or max, got {sense!r}")
    narrative = str(raw.get("narrative") or "")
    variables = _parse_variables(raw.get("variables"), problem_class=problem_class)  # type: ignore[arg-type]
    tolerances = _parse_tolerances(raw.get("tolerances"))
    verification = _parse_verification(raw.get("verification"), variables)
    return ProblemSpec(
        id=problem_id,
        problem_class=problem_class,  # type: ignore[arg-type]
        sense=sense,  # type: ignore[arg-type]
        variables=variables,
        narrative=narrative,
        tolerances=tolerances,
        verification=verification,
        schema=schema,
        source=source,
    )


def _parse_variables(raw: object, *, problem_class: str) -> dict[str, VariableSpec]:
    if not isinstance(raw, dict) or not raw:
        raise ProblemSpecError("variables must be a non-empty mapping")
    parsed: dict[str, VariableSpec] = {}
    for name, spec in raw.items():
        if not isinstance(name, str) or not name.isidentifier():
            raise ProblemSpecError(f"variable name {name!r} is not a valid identifier")
        if not isinstance(spec, dict):
            raise ProblemSpecError(f"variable {name} must be a mapping")
        kind = spec.get("kind")
        if kind not in {"continuous", "integer", "binary"}:
            raise ProblemSpecError(f"variable {name} has unknown kind {kind!r}")
        if problem_class == "lp" and kind != "continuous":
            raise ProblemSpecError(f"lp variable {name} must be continuous")
        if problem_class == "milp" and kind == "continuous":
            # Mixed is allowed in MILP; continuous is fine.
            pass
        lower = _optional_number(spec.get("lower"))
        upper = _optional_number(spec.get("upper"))
        if kind == "binary":
            lower = Fraction(0) if lower is None else lower
            upper = Fraction(1) if upper is None else upper
        parsed[name] = VariableSpec(name=name, kind=kind, lower=lower, upper=upper)
    return parsed


def _parse_tolerances(raw: object) -> Tolerances:
    if raw is None:
        return Tolerances()
    if not isinstance(raw, dict):
        raise ProblemSpecError("tolerances must be a mapping")
    defaults = Tolerances()
    return Tolerances(
        primal_feasibility=float(raw.get("primal_feasibility", defaults.primal_feasibility)),
        objective_abs=float(raw.get("objective_abs", defaults.objective_abs)),
        objective_rel=float(raw.get("objective_rel", defaults.objective_rel)),
        integrality=float(raw.get("integrality", defaults.integrality)),
    )


def _parse_verification(raw: object, variables: dict[str, VariableSpec]) -> VerificationIR | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ProblemSpecError("verification must be a mapping")
    constraints_raw = raw.get("constraints")
    if not isinstance(constraints_raw, list) or not constraints_raw:
        raise ProblemSpecError("verification.constraints must be a non-empty list")
    constraints: list[LinearConstraint] = []
    for item in constraints_raw:
        constraints.append(_parse_constraint(item, variables))
    objective_raw = raw.get("objective")
    if not isinstance(objective_raw, dict) or "terms" not in objective_raw:
        raise ProblemSpecError("verification.objective.terms is required")
    objective = _parse_terms(objective_raw["terms"], variables, where="objective")
    return VerificationIR(constraints=tuple(constraints), objective=objective)


def _parse_constraint(raw: object, variables: dict[str, VariableSpec]) -> LinearConstraint:
    if not isinstance(raw, dict):
        raise ProblemSpecError("each constraint must be a mapping")
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise ProblemSpecError("constraint name is required")
    op = raw.get("op")
    if op not in {"<=", ">=", "=="}:
        raise ProblemSpecError(f"constraint {name} has unsupported op {op!r}")
    if "rhs" not in raw:
        raise ProblemSpecError(f"constraint {name} is missing rhs")
    terms = _parse_terms(raw.get("terms"), variables, where=f"constraint {name}")
    return LinearConstraint(name=name, terms=terms, op=op, rhs=_parse_number(raw["rhs"]))


def _parse_terms(raw: object, variables: dict[str, VariableSpec], *, where: str) -> dict[str, Fraction]:
    if not isinstance(raw, dict) or not raw:
        raise ProblemSpecError(f"{where}: terms must be a non-empty mapping")
    terms: dict[str, Fraction] = {}
    for name, coeff in raw.items():
        if name not in variables:
            raise ProblemSpecError(f"{where}: unknown variable {name!r}")
        terms[str(name)] = _parse_number(coeff)
    return terms


def _require_str(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ProblemSpecError(f"{key} is required")
    return value


def _parse_number(value: object) -> Fraction:
    if isinstance(value, bool) or value is None:
        raise ProblemSpecError(f"invalid numeric value {value!r}")
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, float):
        return Fraction(value).limit_denominator(10_000_000)
    if isinstance(value, str):
        return Fraction(value)
    raise ProblemSpecError(f"invalid numeric value {value!r}")


def _optional_number(value: object) -> Fraction | None:
    if value is None:
        return None
    return _parse_number(value)
