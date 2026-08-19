# Phase 0 report

Date: 2026-08-19  
Probe: `python -m dubito probe`  
Hypothesis: **Independent-formulation disagreement detects formulation bugs.**

## Result

**Holds.** `hypothesis_holds: true`

| Case | Expect | Verdict | agreement | claimed objectives |
|---|---|---|---|---|
| Independent CVXPY vs OR-Tools | agree | agree | 1.0 | 220 / 220 |
| Inverted mix constraint | disagree | disagree | 0.0 | 220 / 200 |
| Missing labor constraint | disagree | disagree | 0.5 | 220 / 240 |
| Wrong table profit (40 vs 50) | disagree | disagree | 0.0 | 220 / 200 |

No false disagreement on the independently written pair. No false agreement on any planted bug.

Hand enumeration of the narrative still says the unique optimum is `(tables=2, chairs=6, profit=220)`. Both OK encodings found that point. That number is a probe oracle, not an input to the checker.

## What each bug looked like

**Inverted mix** (`chairs >= 2*tables` written as `tables >= 2*chairs`).
The OK solution `(2, 6)` is infeasible in the buggy model; the buggy solution `(4, 0)` is infeasible in the OK model. Both exchange directions fail. This is the cheap case the design was betting on.

**Missing labor.** The buggy model keeps the OK solution (agreement 0.5 in that direction) but reports a better claimed optimum `(0, 12, 240)`. Substituting that point into the OK model violates `2*tables + chairs <= 10`. Claimed-optima mismatch plus one-way infeasibility. A missing constraint is not always a two-way feasibility failure; comparing claimed objectives is required.

**Wrong profit.** Same feasible point `(2, 6)`, different linear forms (220 vs 200). Both directions stay feasible; `objective_match` is false. Feasibility-only exchange would have missed this.

## What this does not show

- LLM-written formulations. Phase 0 used independently handwritten encodings because the LLM call shape is still an open decision in PLAN.md §7.
- Correlated bugs. If every backend makes the same mistake, exchange check stays silent. That is why `probes/phase0/z3_spec.py` exists as a third, solver-independent encoding.
- Optimality certificates. The score vector's `guarantee` field says so explicitly.

## Engineering note

CVXPY 1.9 pulls `highspy`. OR-Tools bundles a different HiGHS. They cannot share a process. `load_formulation()` runs each encoding in a subprocess (`python -m dubito._sandbox_worker`). That is a feature of the checker, not a Phase 0 shortcut.

## Next

Phase 1: structured-text input, Z3 on the default path (not just the probe), CLI as the only UI, LP/MILP only.
