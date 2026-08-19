# Problem schema (dubito.problem/v1)

Phase 1 input is structured YAML, not natural language. This file is the
schema. Change it here and in `dubito.problem` together.

## Required fields

| Field | Meaning |
|---|---|
| `schema` | Must be `dubito.problem/v1` |
| `id` | Stable problem id |
| `class` | `lp` or `milp` (Phase 1 only) |
| `sense` | `min` or `max` |
| `variables` | Canonical names used to exchange solutions |
| `narrative` | Human/LLM-facing statement. Solver formulations are written from this, independently |

`variables.<name>.kind` is `continuous`, `integer`, or `binary`. Bounds are optional (`lower`, `upper`).

## `verification` (optional, but this is the SMT path)

A linear constraint set consumed **only** by the verification layer (exact residuals + Z3).

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

## Tolerances

Optional. Defaults and policy live in [tolerances.md](tolerances.md).

## What the schema does not contain

- A solver-neutral model that is mechanically lowered to each backend
- Non-linear / black-box / multi-objective classes (Phase 3)
- Natural language as the only input (later)
