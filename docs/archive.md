# Counterexample archive (`dubito.archive/v1`)

Append-only JSONL. One object per counterexample. This is the format PLAN §7
left open; CEGIS and later knowledge injection join on `problem_id` plus the
hashes, not on file paths.

Write with `dubito.archive.append_counterexamples` or:

```bash
python -m dubito check --problem probes/phase0/furniture.yaml \
  --archive /tmp/dubito.jsonl \
  probes/phase0/formulations/cvxpy_ok.py \
  probes/phase0/bugs/cvxpy_inverted_ratio.py
```

## Record

| Field | Meaning |
|---|---|
| `schema` | `dubito.archive/v1` |
| `problem_id` | Spec `id` |
| `kind` | `infeasible`, `smt_infeasible`, `dual_bound_exceeded`, `local_optimality`, … |
| `assignment` | Exchanged / claimed point when present |
| `formulation_names` | Solver encodings in the run that produced this row |
| `verdict` | Score-vector verdict at write time |
| `narrative_hash` | SHA-256 of the spec narrative |
| `verification_hash` | SHA-256 of a canonical encoding of the verification IR |
| `timestamp` | UTC ISO-8601 |
| `counterexample` | Full counterexample object from the score vector |

Agreeing runs write nothing. CEGIS appends on every disagreeing iteration of
the same file.

## Lessons (`dubito.lessons/v1`)

`python -m dubito lessons --archive path.jsonl` (or `dubito.lessons.distill`)
groups rows by `(problem_id, kind, verification_hash)` and counts them. This is
material for an external agent; dubito does not rewrite prompts.
