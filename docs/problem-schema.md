# Problem schema (dubito.problem/v1)

Phase 1+ input is structured YAML, not natural language. This file is the
schema. Change it here and in `dubito.problem` together.

## Required fields

| Field | Meaning |
|---|---|
| `schema` | Must be `dubito.problem/v1` |
| `id` | Stable problem id |
| `class` | Problem class: `lp`, `milp`, `nlp`, `convex`, `sat`, `blackbox`, `symbolic_regression`, `multiobjective`, `routing`. The router maps this to verification layers, not to a solver. |
| `sense` | `min` or `max` |
| `variables` | Canonical names used to exchange solutions |
| `narrative` | Human/LLM-facing statement. Solver formulations are written from this, independently |

`variables.<name>.kind` is `continuous`, `integer`, or `binary`. Bounds are optional (`lower`, `upper`).

## `verification` (optional, verifier-only)

Consumed **only** by the verification layer. Solver backends must not import this
block or generate CVXPY/OR-Tools/SciPy code from it.

`verification.kind` is `linear` (default) or `residual`.

### `kind: linear` (lp / milp)

A linear constraint set for exact residuals, Z3, LP dual, and resource monotonicity.

```yaml
verification:
  constraints:
    - name: wood
      terms: {tables: 3, chairs: 1}
      op: "<="          # <=, >=, or ==
      rhs: 12
  objective:
    terms: {tables: 50, chairs: 20}
```

`lp` and `milp` must use this kind.

### `kind: residual` (nlp)

Whitelist arithmetic (`+ - * / **`, `abs`, `sqrt`; exponent abs ≤ 8). Evaluated
as a residual witness. P3a does not run Z3 on these expressions.

```yaml
verification:
  kind: residual
  constraints: []
  objective:
    expr: "(1 - x)**2 + 100 * (y - x**2)**2"
```

The narrative is the formulation source; this block is the independent witness.

## `properties` (optional, Hypothesis)

Consumed only by the verification layer.

```yaml
properties:
  local_optimality:
    radius: 2
    max_examples: 40
  resource_monotonicity:
    constraints: [wood, labor]
    max_increase: 5
    max_examples: 20
```

- `local_optimality` samples a neighborhood around an IR-feasible candidate.
  Integer/binary variables use integer offsets (`int(radius)`). Continuous
  NLP variables use a float stencil (and Hypothesis if the grid is large).
  An IR-feasible neighbor with a strictly better objective is a disagreement.
- `resource_monotonicity` requires a **linear** IR. It perturbs the named
  constraint RHS in the relaxing direction and re-solves the IR LP relaxation.
  Formulations that hardcode stocks are not re-solved.

## `determinism` (optional)

```yaml
determinism:
  seed: 0
```

Held on the spec so later stochastic layers can share a seed. Hypothesis
property tests already use `derandomize=True`. Formulation modules do not
read this file; SciPy seeds stay inside each module.

## Dual bound

The dual is built from `verification` only (standard max form, bounds as rows,
`scipy.optimize.linprog`). A claimed max objective above the bound is
impossible. A gap below the bound is allowed for MILP and is reported as
`dual_closed: false`. When an integer-feasible claim matches the LP dual, the
IP is certified against this IR.

## Tolerances

Optional. Defaults and policy live in [tolerances.md](tolerances.md).

## Counterexample archive

See [archive.md](archive.md).

## What the schema does not contain

- A solver-neutral model that is mechanically lowered to each backend
- Implemented KKT / Pareto coverage / SAT pairing / Optuna / PySR (declared in
  [beyond.md](beyond.md); layers are skipped until written)
- Natural language as the only input (later)
- An LLM. External agents write `formulation()` modules and, for CEGIS, a
  `Reformulator` (path map or custom)
