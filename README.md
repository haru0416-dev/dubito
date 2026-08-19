# dubito (working name)

A tool that **doubts solutions**.

Given a mathematical problem, independently formulate it in multiple solvers, swap the solutions, check them against a spec-derived Z3 encoding, and emit a deterministic score vector. The point is not to win an accuracy contest. The point is to make wrong answers detectable — including as an LLM-free fitness function for evolutionary agents.

The product name is unset on purpose. Phase 0 confirmed the exchange-check hypothesis. Phase 1 is the LP/MILP MVP.

```bash
pip install -e ".[dev]"
# system GLPK is required for CVXPY MILP (libglpk). Do not install `highspy`
# alongside `ortools`; the two ship incompatible HiGHS libraries.
python -m dubito check --problem probes/phase0/furniture.yaml \
  probes/phase0/formulations/cvxpy_ok.py \
  probes/phase0/formulations/ortools_ok.py
python -m dubito probe
python -m pytest
```

## Phase 0

Independent CVXPY vs OR-Tools encodings of one MILP, plus planted bugs. Hypothesis holds. See [probes/phase0/REPORT.md](probes/phase0/REPORT.md).

## Phase 1

Structured input is `dubito.problem/v1` YAML ([docs/problem-schema.md](docs/problem-schema.md)). The `verification` block is a linear IR for Z3 only — formulation modules must not compile from it. `verify()` runs exchange check then SMT. Correlated bugs (the same mistake in every backend) survive exchange and fail SMT.

LLM calls are out of process: an external agent writes `formulation()` modules. This tool does not call a model.

## Score vector

`verdict`, `agreement`, per-solver feasibility, claimed objectives, optimality status, `smt_feasible`, `smt_objective_match`, counterexamples, runtimes, explicit `guarantee` and `verification_strength` (`exchange`, `smt`, or `exchange+smt`). Natural language is not the output.

`dubito.evaluator.evaluate` maps this to OpenEvolve metrics (`combined_score` is 1 only on `agree`). Optional env: `DUBITO_PROBLEM`, `DUBITO_PEER_FORMULATIONS`.

Tolerances: [docs/tolerances.md](docs/tolerances.md).

## Layout

```
src/dubito/           exchange, SMT pipeline, score vector, CLI, evaluator
probes/phase0/        furniture MILP, independent formulations, planted bugs
docs/problem-schema.md
examples/openevolve/  evaluate(program_path) re-export
```

Each formulation runs in a subprocess so CVXPY/HiGHS and OR-Tools never share an address space.
