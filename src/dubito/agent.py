"""Agent-facing views of a problem and a score. No LLM in-process.

These payloads are what an external model should read. They never include the
verification IR (that block is a witness, not a compiler input).
"""

from __future__ import annotations

from typing import Any, Mapping

from dubito.classes import PROFILES
from dubito.model import ScoreVector
from dubito.problem import ProblemSpec, VariableSpec
from dubito.router import capabilities, route

AGENT_SCHEMA = "dubito.agent/v1"
SPEC_SCHEMA = "dubito.spec/v1"
CONTRACT_SCHEMA = "dubito.contract/v1"
PLAYBOOK_SCHEMA = "dubito.playbook/v1"

INSTRUCTIONS = (
    "dubito is a verifier of formulation code, not a solver. "
    "Call dubito_spec, then dubito_contract, write at least two independent "
    "modules from the narrative only, then dubito_check. Never copy the YAML "
    "verification block into solvers. On disagree, rewrite the named module "
    "using agent.repair. agree is not a global proof; report agent.ceiling. "
    "A complaint that something is slow is not a spec: do not only patch the "
    "nearby hot path."
)

KIND_HINTS: dict[str, str] = {
    "code_import": (
        "This module imports the verification IR or problem YAML loader. "
        "Delete that import and rewrite constraints from the narrative."
    ),
    "code_peer_import": (
        "This module imports another formulation. Write an independent encoding."
    ),
    "code_parse": (
        "This module did not parse. Fix the Python, then check again."
    ),
    "code_no_factory": (
        "Export formulation() -> Formulation. See dubito_contract."
    ),
    "code_name": (
        "Do not name a module types.py."
    ),
    "infeasible": (
        "A peer assignment is infeasible here. Rewrite this encoding from the "
        "narrative so the exchanged point is feasible, or the peer is wrong."
    ),
    "objective_mismatch": (
        "Same assignment, different objective values. Check profit/cost coefficients "
        "in the named formulation; do not copy them from the verification YAML."
    ),
    "claimed_optima_mismatch": (
        "Solvers claim different optimal values. At least one encoding of the "
        "objective or feasible region is wrong."
    ),
    "smt_infeasible": (
        "This assignment is feasible in the solver but not in the independent "
        "verification IR. Rewrite that solver's constraints from the narrative."
    ),
    "smt_objective_mismatch": (
        "Claimed objective does not match the verification IR objective. Fix "
        "coefficients in that formulation."
    ),
    "residual_infeasible": (
        "This assignment fails the residual witness. Rewrite the nonlinear "
        "encoding from the narrative, not from the YAML expr."
    ),
    "residual_objective_mismatch": (
        "Claimed objective does not match the residual witness. Fix the "
        "objective in that formulation."
    ),
    "dual_bound_exceeded": (
        "Claimed objective beats the verification-IR dual. The formulation is "
        "too loose (missing constraint) or the objective is wrong."
    ),
    "local_optimality": (
        "A nearby IR-feasible point is better. The claimed point is not locally "
        "optimal against the witness."
    ),
    "resource_monotonicity": (
        "The verification IR itself failed resource monotonicity. Do not patch "
        "formulations; the spec witness is wrong."
    ),
}

_DO_NOT = (
    "Do not import, parse, or copy the YAML verification block into formulations.",
    "Do not compile one shared constraint IR into every solver.",
    "Do not treat agree as a global optimality proof; report the ceiling.",
    "Do not treat a nearby speedup as a global improvement; report the ceiling.",
    "Do not name a module types.py (stdlib shadowing).",
)


def spec_for_agent(problem: ProblemSpec, *, n_formulations: int = 2) -> dict[str, Any]:
    """Narrative + variable interface + ceiling. Never the verification matrix."""

    routed = route(problem, n_formulations=n_formulations)
    variables = {name: _variable_public(spec) for name, spec in problem.variables.items()}
    return {
        "schema": SPEC_SCHEMA,
        "id": problem.id,
        "class": problem.problem_class,
        "sense": problem.sense,
        "variables": variables,
        "narrative": problem.narrative,
        "ceiling": routed.profile.ceiling,
        "layers_planned": list(routed.planned),
        "backends_advisory": list(capabilities(problem.problem_class)),
        "determinism": {"seed": problem.determinism.seed},
        "verification_present": problem.verification is not None,
        "verification_kind": getattr(problem.verification, "kind", None),
        "invariants": list(_DO_NOT),
        "next": [
            {"tool": "dubito_contract", "why": "module shape and adapter to subclass"},
            {"tool": "dubito_check", "why": "after writing two independent formulation() modules"},
        ],
    }


def formulation_contract(
    problem: ProblemSpec | None = None,
    *,
    problem_class: str | None = None,
) -> dict[str, Any]:
    """How to write a formulation() module. No constraint numbers."""

    cls = problem.problem_class if problem is not None else problem_class
    if not cls:
        raise ValueError("formulation_contract needs a problem or problem_class")
    if cls not in PROFILES:
        raise KeyError(f"unknown problem class {cls!r}")
    profile = PROFILES[cls]
    names = problem.variable_names if problem is not None else ("x",)
    sense = problem.sense if problem is not None else "min"
    problem_id = problem.id if problem is not None else "problem-id"
    kinds = (
        {name: problem.variables[name].kind for name in names}
        if problem is not None
        else {names[0]: "continuous"}
    )
    primary = profile.backends[0] if profile.backends else "cvxpy"
    return {
        "schema": CONTRACT_SCHEMA,
        "class": cls,
        "problem_id": problem_id,
        "sense": sense,
        "variables": list(names),
        "variable_kinds": kinds,
        "module_must_export": "formulation() -> Formulation",
        "class_attrs": ["name", "variables", "sense", "problem_id"],
        "methods": [
            "solve() -> SolveResult with assignment keys equal to variables",
            "check(assignment, tol) -> CheckResult (used by exchange)",
        ],
        "adapters": {
            "cvxpy": "subclass CvxpyFormulation; implement _problem() -> (cp.Problem, var_map)",
            "ortools": "subclass OrtoolsFormulation; implement _build() -> (solver, var_map)",
            "scipy": "subclass ScipyFormulation; implement _objective(vec) -> float",
        },
        "choose_adapter": primary,
        "backends_advisory": list(profile.backends),
        "forbidden": [
            "from dubito.problem import as_linear_ir, as_residual_ir, load_problem",
            "yaml.safe_load of the problem file inside the formulation module",
            "importing constraint bodies from a shared helper used by every backend",
        ],
        "skeleton": _skeleton(primary, problem_id, names, sense, kinds),
        "second_encoding": (
            "Write a second module with a different adapter (or a different "
            "algorithm) from the same narrative. Independent bugs are the point."
        ),
    }


def playbook() -> dict[str, Any]:
    return {
        "schema": PLAYBOOK_SCHEMA,
        "instructions": INSTRUCTIONS,
        "loop": [
            "dubito_spec with the problem YAML path",
            "dubito_contract (same problem) and pick two advisory backends",
            "Write two files exporting formulation(); constraints from narrative only",
            "dubito_check inspects the source (no IR imports), then runs solvers; read result.agent",
            "On disagree: rewrite the named module using agent.repair; check again",
            "On agree: stop and quote agent.ceiling; do not claim more",
            "Optional: dubito_lessons on the archive after several disagreements",
        ],
        "tools_order": [
            "dubito_playbook",
            "dubito_spec",
            "dubito_contract",
            "dubito_profile",
            "dubito_check",
            "dubito_lessons",
        ],
        "do_not": list(_DO_NOT),
        "cegis": (
            "dubito_cegis has no in-process model. After you rewrite a file, call "
            "dubito_check again. --replace is a path map for tests, not an LLM."
        ),
        "when_told_heavy": {
            "cannot": (
                "dubito does not derive a faster design from 'this feature is "
                "slow'. That sentence is not a problem spec."
            ),
            "local_trap": (
                "Models almost always patch the nearby hot path (cache, fewer "
                "Hypothesis examples, skip a layer). That is the same failure "
                "mode as local_optimality: a neighbor looks better, the dual "
                "or residual ceiling was never asked."
            ),
            "if_measurable": [
                "Write what heavy means as an objective and what must not break as constraints (narrative only).",
                "Encode two independent formulations of that tradeoff, not two edits of the same function.",
                "dubito_check: a better IR-feasible neighbor is disagree; beating the dual is a missing constraint.",
                "agree still only means the class ceiling (often local / residual / dual of this IR).",
            ],
            "do_not": [
                "Skip verification layers as the only speedup without a spec.",
                "Treat a local patch that still agrees with itself as globally better.",
            ],
        },
    }


def agent_brief(
    score: ScoreVector,
    *,
    seen_kinds: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Next-action brief an external model can follow without the full score."""

    ceiling = ""
    if isinstance(score.profile, dict):
        ceiling = str(score.profile.get("ceiling") or "")
    if not ceiling:
        ceiling = score.guarantee

    kinds: list[str] = []
    repair: list[str] = []
    next_actions: list[dict[str, Any]] = []
    seen_solvers: set[str] = set()

    for item in score.counterexamples:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "unknown")
        kinds.append(kind)
        hint = KIND_HINTS.get(
            kind,
            "Rewrite the named formulation from the narrative, not from the verification IR.",
        )
        for solver in _counterexample_solvers(item):
            repair.append(f"{solver}: {hint}")
            if solver not in seen_solvers and score.verdict != "agree":
                seen_solvers.add(solver)
                next_actions.append(
                    {
                        "action": "rewrite_formulation",
                        "solver": solver,
                        "kind": kind,
                        "reason": hint,
                    }
                )
        if not _counterexample_solvers(item):
            repair.append(hint)

    if score.verdict == "agree":
        next_actions = [{"action": "stop", "reason": "verdict is agree", "report": ceiling}]
    elif score.verdict == "error":
        errored = [name for name, status in score.optimality_status.items() if status == "error"]
    next_actions = [
            {
                "action": "fix_runtime",
                "solvers": errored,
                "reason": "a formulation returned status error; read notes and traceback",
            }
        ]
    elif not next_actions:
        next_actions = [{"action": "rewrite_formulation", "reason": f"verdict is {score.verdict}"}]

    unique_kinds = sorted(set(kinds))
    payload: dict[str, Any] = {
        "schema": AGENT_SCHEMA,
        "stop": score.verdict == "agree",
        "verdict": score.verdict,
        "ceiling": ceiling,
        "do_not": list(_DO_NOT),
        "next": next_actions,
        "repair": repair[:16],
        "kinds": unique_kinds,
    }
    if seen_kinds:
        payload["seen_kinds"] = {
            kind: int(seen_kinds[kind]) for kind in unique_kinds if kind in seen_kinds
        }
    return payload


def score_for_agent(score: ScoreVector, *, compact: bool = True) -> dict[str, Any]:
    brief = agent_brief(score)
    if compact:
        return {
            "problem_id": score.problem_id,
            "verdict": score.verdict,
            "verification_strength": score.verification_strength,
            "guarantee": score.guarantee,
            "feasible": dict(score.feasible),
            "objective": dict(score.objective),
            "claimed_optima_match": score.claimed_optima_match,
            "counterexamples": list(score.counterexamples),
            "layers": dict(score.layers),
            "code_ok": dict(score.code_ok),
            "notes": list(score.notes)[:12],
            "agent": brief,
        }
    payload = score.to_dict()
    payload["agent"] = brief
    return payload


def _variable_public(spec: VariableSpec) -> dict[str, Any]:
    return {
        "kind": spec.kind,
        "lower": None if spec.lower is None else float(spec.lower),
        "upper": None if spec.upper is None else float(spec.upper),
    }


def _counterexample_solvers(item: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("solver", "source", "target"):
        value = item.get(key)
        if isinstance(value, str) and value:
            names.append(value)
    direction = item.get("direction")
    if isinstance(direction, dict):
        for key in ("source", "target"):
            value = direction.get(key)
            if isinstance(value, str) and value and value not in names:
                names.append(value)
    return names


def _skeleton(
    adapter: str,
    problem_id: str,
    names: tuple[str, ...],
    sense: str,
    kinds: Mapping[str, str],
) -> str:
    var_tuple = ", ".join(repr(name) for name in names)
    if adapter == "scipy":
        body = "\n".join(
            f"        {name} = float(vec[{index}])" for index, name in enumerate(names)
        )
        return (
            '"""Independent SciPy encoding. Constraints from the narrative only."""\n'
            "from __future__ import annotations\n\n"
            "import numpy as np\n"
            "from dubito.backends.scipy_backend import ScipyFormulation\n\n\n"
            "class Formulation(ScipyFormulation):\n"
            f'    name = "scipy_{problem_id}"\n'
            f'    problem_id = "{problem_id}"\n'
            f"    variables = ({var_tuple},)\n"
            f'    sense = "{sense}"\n\n'
            "    def _objective(self, vec: np.ndarray) -> float:\n"
            f"{body}\n"
            "        raise NotImplementedError(\"encode the narrative here\")\n\n\n"
            "def formulation() -> Formulation:\n"
            "    return Formulation()\n"
        )
    if adapter == "ortools":
        decls = "\n".join(
            _ortools_decl(name, kinds.get(name, "continuous")) for name in names
        )
        return (
            '"""Independent OR-Tools encoding. Constraints from the narrative only."""\n'
            "from __future__ import annotations\n\n"
            "from ortools.linear_solver import pywraplp\n"
            "from dubito.backends.ortools_backend import OrtoolsFormulation\n\n\n"
            "class Formulation(OrtoolsFormulation):\n"
            f'    name = "ortools_{problem_id}"\n'
            f'    problem_id = "{problem_id}"\n'
            f"    variables = ({var_tuple},)\n"
            f'    sense = "{sense}"\n\n'
            "    def _build(self):\n"
            "        solver = pywraplp.Solver.CreateSolver(self.solver_id)\n"
            f"{decls}\n"
            "        # objective and constraints from the NARRATIVE only\n"
            "        raise NotImplementedError(\"encode the narrative here\")\n\n\n"
            "def formulation() -> Formulation:\n"
            "    return Formulation()\n"
        )
    decls = "\n".join(_cvxpy_decl(name, kinds.get(name, "continuous")) for name in names)
    return (
        '"""Independent CVXPY encoding. Constraints from the narrative only."""\n'
        "from __future__ import annotations\n\n"
        "import cvxpy as cp\n"
        "from dubito.backends.cvxpy_backend import CvxpyFormulation\n\n\n"
        "class Formulation(CvxpyFormulation):\n"
        f'    name = "cvxpy_{problem_id}"\n'
        f'    problem_id = "{problem_id}"\n'
        f"    variables = ({var_tuple},)\n"
        f'    sense = "{sense}"\n\n'
        "    def _problem(self):\n"
        f"{decls}\n"
        "        # objective and constraints from the NARRATIVE, never the YAML verification block\n"
        "        raise NotImplementedError(\"encode the narrative here\")\n\n\n"
        "def formulation() -> Formulation:\n"
        "    return Formulation()\n"
    )


def _cvxpy_decl(name: str, kind: str) -> str:
    if kind == "binary":
        return f"        {name} = cp.Variable(boolean=True, name={name!r})"
    if kind == "integer":
        return f"        {name} = cp.Variable(integer=True, name={name!r}, nonneg=True)"
    return f"        {name} = cp.Variable(name={name!r})"


def _ortools_decl(name: str, kind: str) -> str:
    if kind in {"integer", "binary"}:
        return f"        {name} = solver.IntVar(0, solver.infinity(), {name!r})"
    return f"        {name} = solver.NumVar(0, solver.infinity(), {name!r})"
