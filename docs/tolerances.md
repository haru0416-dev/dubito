# Numeric tolerances

False disagreements from floating point are a first-class risk. This file is the
Phase 0/1 policy. Change it in code (`dubito.model.Tolerances`) and here together.

## Defaults

| Field | Default | Role |
|---|---|---|
| `primal_feasibility` | `1e-6` | Constraint residual / bound violation |
| `objective_abs` | `1e-6` | Absolute objective gap |
| `objective_rel` | `1e-6` | Relative objective gap vs `max(1, |a|, |b|)` |
| `integrality` | `1e-8` | Distance to nearest integer before rounding |

Two numbers `a, b` match iff `|a-b| <= max(objective_abs, objective_rel * scale)`
with `scale = max(1, |a|, |b|)`.

## MILP exact path

When a variable is integer/binary and `|x - round(x)| <= integrality`, the
exchange checker treats `x` as that integer. Z3 assignment checks then use
exact integer equality, not a float box.

This is why Phase 1 is LP/MILP-first: integer data plus integer variables can
be compared without a dual-gap story. Phase 2 still emits a dual bound from the
verification IR; a remaining gap is reported rather than treated as agreement
failure, except when a claimed objective beats the bound.

## What a disagreement means

A failed exchange is **not** automatically a solver bug. The default
interpretation is *formulation mismatch* (the two programs are not the same
problem). Numerical false positives should be hunted by tightening/loosening
these four numbers on a known-equivalent pair before blaming a backend.

## What agreement does not mean

Agreement does not prove optimality. Correlated formulation bugs (the same
wrong constraint in every backend) survive exchange check. That is why the
verification layer rebuilds constraints in Z3 from the spec, on a separate path.
