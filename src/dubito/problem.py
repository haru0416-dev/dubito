from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal, Mapping

import yaml

from dubito.classes import PROBLEM_CLASSES
from dubito.model import Sense, Tolerances, VarKind

SCHEMA_V1 = "dubito.problem/v1"
SUPPORTED_CLASSES = frozenset(PROBLEM_CLASSES)
ConstraintOp = Literal["<=", ">=", "=="]
VerificationKind = Literal["linear", "residual"]


class ProblemSpecError(ValueError):
    """Raised when a problem YAML file does not match the schema."""


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
    kind: VerificationKind = "linear"


@dataclass(frozen=True)
class ResidualConstraint:
    name: str
    expr: str
    op: ConstraintOp
    rhs: Fraction


@dataclass(frozen=True)
class ResidualIR:
    """Nonlinear residual witness. Not a compiler input for SciPy/CVXPY."""

    constraints: tuple[ResidualConstraint, ...]
    objective_expr: str
    kind: VerificationKind = "residual"


@dataclass(frozen=True)
class LocalOptimalitySpec:
    radius: float = 2.0
    max_examples: int = 40


@dataclass(frozen=True)
class DeterminismSpec:
    seed: int = 0


@dataclass(frozen=True)
class ResourceMonotonicitySpec:
    constraints: tuple[str, ...]
    max_increase: int = 5
    max_examples: int = 20


@dataclass(frozen=True)
class PropertySpec:
    """Optional Hypothesis / neighborhood checks. Consumed only by verification."""

    local_optimality: LocalOptimalitySpec | None = None
    resource_monotonicity: ResourceMonotonicitySpec | None = None


@dataclass(frozen=True)
class ProblemSpec:
    id: str
    problem_class: str
    sense: Sense
    variables: dict[str, VariableSpec]
    narrative: str
    tolerances: Tolerances
    verification: VerificationIR | ResidualIR | None
    schema: str = SCHEMA_V1
    source: str | None = None
    properties: PropertySpec | None = None
    determinism: DeterminismSpec = field(default_factory=DeterminismSpec)

    @property
    def variable_names(self) -> tuple[str, ...]:
        return tuple(self.variables)


def as_linear_ir(problem: ProblemSpec) -> VerificationIR | None:
    ir = problem.verification
    if isinstance(ir, VerificationIR):
        return ir
    return None


def as_residual_ir(problem: ProblemSpec) -> ResidualIR | None:
    ir = problem.verification
    if isinstance(ir, ResidualIR):
        return ir
    return None


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
            f"class {problem_class!r} is not a supported class; supported: {sorted(SUPPORTED_CLASSES)}"
        )
    sense = _require_str(raw, "sense")
    if sense not in {"min", "max"}:
        raise ProblemSpecError(f"sense must be min or max, got {sense!r}")
    narrative = str(raw.get("narrative") or "")
    variables = _parse_variables(raw.get("variables"), problem_class=problem_class)  # type: ignore[arg-type]
    tolerances = _parse_tolerances(raw.get("tolerances"))
    verification = _parse_verification(raw.get("verification"), variables)
    _validate_class_ir(problem_class, verification)
    properties = _parse_properties(raw.get("properties"), verification)
    return ProblemSpec(
        id=problem_id,
        problem_class=problem_class,
        sense=sense,  # type: ignore[arg-type]
        variables=variables,
        narrative=narrative,
        tolerances=tolerances,
        verification=verification,
        schema=schema,
        source=source,
        properties=properties,
        determinism=_parse_determinism(raw.get("determinism")),
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


def _parse_verification(
    raw: object, variables: dict[str, VariableSpec]
) -> VerificationIR | ResidualIR | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ProblemSpecError("verification must be a mapping")
    kind = str(raw.get("kind") or "linear")
    if kind == "linear":
        return _parse_linear_verification(raw, variables)
    if kind == "residual":
        return _parse_residual_verification(raw, variables)
    raise ProblemSpecError(f"verification.kind {kind!r} is not supported")


def _parse_linear_verification(
    raw: Mapping[str, Any], variables: dict[str, VariableSpec]
) -> VerificationIR:
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
    return VerificationIR(constraints=tuple(constraints), objective=objective, kind="linear")


def _parse_residual_verification(
    raw: Mapping[str, Any], variables: dict[str, VariableSpec]
) -> ResidualIR:
    from dubito.expr import ExprError, compile_expr

    names = tuple(variables)
    constraints_raw = raw.get("constraints") or []
    if not isinstance(constraints_raw, list):
        raise ProblemSpecError("verification.constraints must be a list")
    constraints: list[ResidualConstraint] = []
    for item in constraints_raw:
        constraints.append(_parse_residual_constraint(item, names))
    objective_raw = raw.get("objective")
    if not isinstance(objective_raw, dict) or "expr" not in objective_raw:
        raise ProblemSpecError("verification.objective.expr is required for kind residual")
    expr = objective_raw["expr"]
    if not isinstance(expr, str) or not expr.strip():
        raise ProblemSpecError("verification.objective.expr must be a non-empty string")
    try:
        compile_expr(expr, names)
    except ExprError as exc:
        raise ProblemSpecError(str(exc)) from exc
    return ResidualIR(constraints=tuple(constraints), objective_expr=expr, kind="residual")


def _parse_residual_constraint(raw: object, names: tuple[str, ...]) -> ResidualConstraint:
    from dubito.expr import ExprError, compile_expr

    if not isinstance(raw, dict):
        raise ProblemSpecError("each residual constraint must be a mapping")
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise ProblemSpecError("constraint name is required")
    op = raw.get("op")
    if op not in {"<=", ">=", "=="}:
        raise ProblemSpecError(f"constraint {name} has unsupported op {op!r}")
    expr = raw.get("expr")
    if not isinstance(expr, str) or not expr.strip():
        raise ProblemSpecError(f"constraint {name} needs expr")
    try:
        compile_expr(expr, names)
    except ExprError as exc:
        raise ProblemSpecError(str(exc)) from exc
    if "rhs" not in raw:
        raise ProblemSpecError(f"constraint {name} is missing rhs")
    return ResidualConstraint(name=name, expr=expr, op=op, rhs=_parse_number(raw["rhs"]))


def _validate_class_ir(problem_class: str, ir: VerificationIR | ResidualIR | None) -> None:
    if ir is None:
        return
    if problem_class in {"lp", "milp"} and not isinstance(ir, VerificationIR):
        raise ProblemSpecError("lp/milp verification must be kind linear")
    if problem_class == "nlp" and not isinstance(ir, ResidualIR):
        raise ProblemSpecError("nlp verification must be kind residual")


def _parse_determinism(raw: object) -> DeterminismSpec:
    if raw is None:
        return DeterminismSpec()
    if not isinstance(raw, dict):
        raise ProblemSpecError("determinism must be a mapping")
    unknown = set(raw) - {"seed"}
    if unknown:
        raise ProblemSpecError(f"unknown determinism keys: {sorted(unknown)}")
    seed = int(raw.get("seed", 0))
    return DeterminismSpec(seed=seed)


def _parse_properties(
    raw: object, verification: VerificationIR | ResidualIR | None
) -> PropertySpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or not raw:
        raise ProblemSpecError("properties must be a mapping")
    unknown = set(raw) - {"local_optimality", "resource_monotonicity"}
    if unknown:
        raise ProblemSpecError(f"unknown properties keys: {sorted(unknown)}")
    local = _parse_local_optimality(raw.get("local_optimality"))
    mono = _parse_resource_monotonicity(raw.get("resource_monotonicity"), verification)
    if local is None and mono is None:
        return None
    return PropertySpec(local_optimality=local, resource_monotonicity=mono)


def _parse_local_optimality(raw: object) -> LocalOptimalitySpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ProblemSpecError("properties.local_optimality must be a mapping")
    radius = float(raw.get("radius", 2))
    if "samples" in raw and "max_examples" not in raw:
        max_examples = int(raw["samples"])
    else:
        max_examples = int(raw.get("max_examples", 40))
    unknown = set(raw) - {"radius", "max_examples", "samples"}
    if unknown:
        raise ProblemSpecError(f"unknown local_optimality keys: {sorted(unknown)}")
    if radius <= 0:
        raise ProblemSpecError("local_optimality.radius must be > 0")
    if max_examples < 1:
        raise ProblemSpecError("local_optimality.max_examples must be >= 1")
    return LocalOptimalitySpec(radius=radius, max_examples=max_examples)


def _parse_resource_monotonicity(
    raw: object, verification: VerificationIR | ResidualIR | None
) -> ResourceMonotonicitySpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ProblemSpecError("properties.resource_monotonicity must be a mapping")
    names = raw.get("constraints")
    if not isinstance(names, list) or not names or not all(isinstance(item, str) for item in names):
        raise ProblemSpecError("resource_monotonicity.constraints must be a non-empty list of names")
    if not isinstance(verification, VerificationIR):
        raise ProblemSpecError("resource_monotonicity requires a linear verification IR")
    known = {constraint.name for constraint in verification.constraints}
    missing = [name for name in names if name not in known]
    if missing:
        raise ProblemSpecError(f"resource_monotonicity unknown constraints: {missing}")
    max_increase = int(raw.get("max_increase", 5))
    max_examples = int(raw.get("max_examples", 20))
    if max_increase < 0:
        raise ProblemSpecError("resource_monotonicity.max_increase must be >= 0")
    if max_examples < 1:
        raise ProblemSpecError("resource_monotonicity.max_examples must be >= 1")
    return ResourceMonotonicitySpec(
        constraints=tuple(str(name) for name in names),
        max_increase=max_increase,
        max_examples=max_examples,
    )


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
