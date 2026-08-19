# Problem schema (dubito.problem/v1)

Phase 1+ input is structured YAML, not natural language. This file is the
schema. Change it here and in `dubito.problem` together.

## Required fields

| Field | Meaning |
|---|---|
| `schema` | Must be `dubito.problem/v1` |
| `id` | Stable problem id |
| `class` | `lp` or `milp` (Phase 1–2) |
| `sense` | `min` or `max` |
| `variables` | Canonical names used to exchange solutions |
| `narrative` | Human/LLM-facing statement. Solver formulations are written from this, independently |

`variables.<name>.kind` is `continuous`, `integer`, or `binary`. Bounds are optional (`lower`, `upper`).

## `verification` (optional, but this is the SMT / dual path)

A linear constraint set consumed **only** by the verification layer (exact residuals, Z3, LP dual, Hypothesis).

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

Solver backends must not import this block, compile it, or generate CVXPY/OR-Tools
code from it. If they did, a spec bug would infect every backend and exchange
check would go blind. The narrative is the formulation source; this block is
the independent witness.

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

- `local_optimality` samples integer offsets around an SMT-feasible candidate.
  An IR-feasible neighbor with a strictly better objective is a disagreement.
  Small neighborhoods are enumerated exhaustively; larger ones use Hypothesis
  with `derandomize=True`.
- `resource_monotonicity` perturbs the named IR constraint RHS in the relaxing
  direction and re-solves the **IR LP relaxation**. Formulations that hardcode
  stocks are not re-solved. A falling (max) or rising (min) LP opt fails the
  spec, not a solver encoding.

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
- Non-linear / black-box / multi-objective classes (Phase 3)
- Natural language as the only input (later)
- An LLM. External agents write `formulation()` modules and, for CEGIS, a
  `Reformulator` (path map or custom)
