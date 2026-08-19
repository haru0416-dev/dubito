# dubito (working name)

A tool that **doubts solutions**.

Given a mathematical problem, independently formulate it in multiple solvers, swap the solutions, and emit a deterministic score vector. The point is not to win an accuracy contest. The point is to make wrong answers detectable — including as an LLM-free fitness function for evolutionary agents.

The product name is unset on purpose. This repository exists to run Phase 0 of [PLAN.md](PLAN.md).

## Phase 0 hypothesis

> If two solvers are formulated independently, disagreement under solution exchange detects formulation bugs.

The probe does **not** call an LLM (that wiring is still an open decision in the plan). It uses two independently written encodings of one MILP plus three planted bugs.

```bash
pip install -e ".[dev]"
# system GLPK is required for CVXPY MILP (libglpk). Do not install `highspy`
# alongside `ortools`; the two ship incompatible HiGHS libraries.
python -m dubito probe
python -m pytest
```

Expected Phase 0 outcome: `hypothesis_holds: true`. Confirmed 2026-08-19; see [probes/phase0/REPORT.md](probes/phase0/REPORT.md).

## What is in the score vector

`verdict`, `agreement`, per-solver feasibility, claimed objectives, optimality status, counterexamples, runtimes, explicit `guarantee`. Natural language is not the output. This dict is what `dubito.evaluator.evaluate` turns into OpenEvolve metrics (`combined_score` is 1 only on `agree`).

Tolerances are specified in [docs/tolerances.md](docs/tolerances.md). Agreement is not a proof of optimality; correlated bugs in every backend are invisible to exchange check. Z3 encodings live on a separate path (`probes/phase0/z3_spec.py`) and are the start of the verification layer.

## Layout

```
src/dubito/           exchange checker, score vector, CLI, evaluator adapter
probes/phase0/        one narrative MILP, two OK formulations, three planted bugs
examples/openevolve/  evaluate(program_path) re-export
```

Formulation modules export `formulation()` and must not compile from a shared constraint IR. Canonical variable names are the only shared surface. `python -m dubito check` runs each formulation in a subprocess so CVXPY/HiGHS and OR-Tools never share an address space.

## CLI

```bash
python -m dubito check \
  probes/phase0/formulations/cvxpy_ok.py \
  probes/phase0/formulations/ortools_ok.py
```

Exit 0 on `agree`, 1 otherwise. JSON on stdout.
