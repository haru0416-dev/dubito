# dubito (working name)

A tool that **doubts solutions**.

Given a mathematical problem, independently formulate it in multiple solvers, swap the solutions, check them against a spec-derived Z3 encoding, and emit a deterministic score vector. The point is not to win an accuracy contest. The point is to make wrong answers detectable — including as an LLM-free fitness function for evolutionary agents.

The product name is unset on purpose. Phase 0 confirmed the exchange-check hypothesis. Phase 1 is the LP/MILP MVP. Phase 2 adds dual bounds, Hypothesis properties, a JSONL counterexample archive, and an LLM-free CEGIS loop. Phase 3 routes verification layers by problem class and adds residual NLP. Phase 4/5 add tool descriptors and an archive distiller.

```bash
pip install -e ".[dev]"
# system GLPK is required for CVXPY MILP (libglpk). Do not install `highspy`
# alongside `ortools`; the two ship incompatible HiGHS libraries.
python -m dubito check --problem probes/phase0/furniture.yaml \
  probes/phase0/formulations/cvxpy_ok.py \
  probes/phase0/formulations/ortools_ok.py
python -m dubito check --problem probes/phase3/rosenbrock.yaml \
  probes/phase3/formulations/scipy_nelder_mead.py \
  probes/phase3/formulations/scipy_lbfgsb.py
python -m dubito profile --problem probes/phase3/rosenbrock.yaml --formulations 2
python -m dubito tools
python -m dubito probe
python -m dubito cegis --problem probes/phase0/furniture.yaml --max-iters 3 \
  --replace cvxpy_inverted_ratio.py=ortools_ok.py \
  probes/phase0/formulations/cvxpy_ok.py \
  probes/phase0/bugs/cvxpy_inverted_ratio.py
python -m pytest
```

## Phase 0

Independent CVXPY vs OR-Tools encodings of one MILP, plus planted bugs. Hypothesis holds. See [probes/phase0/REPORT.md](probes/phase0/REPORT.md).

## Phase 1

Structured input is `dubito.problem/v1` YAML ([docs/problem-schema.md](docs/problem-schema.md)). The `verification` block is a linear IR for Z3 only — formulation modules must not compile from it. `verify()` runs exchange check then SMT. Correlated bugs (the same mistake in every backend) survive exchange and fail SMT.

## Phase 2

`verify()` continues past SMT: dual of the verification-IR LP relaxation, then Hypothesis properties from the spec `properties` block. A claimed max objective above the dual is a disagreement; a gap below it is allowed for MILP. An integer-feasible point that matches the LP bound is IP-optimal against this IR.

CEGIS (`python -m dubito cegis`) archives counterexamples and applies a `Reformulator`. There is still no in-process LLM: `--replace buggy.py=ok.py` is a path map for tests and external agents. Archive format: [docs/archive.md](docs/archive.md).

## Phase 3

The router chooses **verification layers**, not which solver to run. Formulations stay independently written. `lp`/`milp` keep exchange+SMT+dual+properties. `nlp` runs exchange+residual+properties (no Z3, no LP dual). Other classes are declared; unimplemented layers show up as `skipped:not-implemented`. Residual IR is a whitelist arithmetic witness (`docs/beyond.md`). Probe: [probes/phase3/PROBLEM.md](probes/phase3/PROBLEM.md).

## Phase 4 / 5

`python -m dubito tools` prints MCP-style descriptors (no SDK). `python -m dubito lessons --archive …` groups archive rows into `dubito.lessons/v1`. `determinism.seed` is on the problem spec.

## Score vector

`verdict`, `agreement`, per-solver feasibility, claimed objectives, optimality status, `smt_feasible`, `smt_objective_match`, `dual_bound` / `dual_gap` / `dual_closed`, `residual_feasible` / `residual_objective_match`, `properties_ok`, `layers`, `profile`, counterexamples, runtimes, explicit `guarantee` and `verification_strength` (the `+` join of layers that `ran`). Natural language is not the output.

`dubito.evaluator.evaluate` maps this to OpenEvolve metrics (`combined_score` is 1 only on `agree`). Optional env: `DUBITO_PROBLEM`, `DUBITO_PEER_FORMULATIONS`.

Tolerances: [docs/tolerances.md](docs/tolerances.md).

## Layout

```
src/dubito/           exchange, SMT, dual, residual, router, CEGIS, archive, lessons, faces, CLI, evaluator
probes/phase0/        furniture MILP, independent formulations, planted bugs
probes/phase3/        Rosenbrock NLP, SciPy formulations, shifted-valley bug
docs/problem-schema.md
docs/archive.md
docs/beyond.md
examples/openevolve/  evaluate(program_path) re-export
```

Each formulation runs in a subprocess so CVXPY/HiGHS and OR-Tools never share an address space.
