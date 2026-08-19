# rosenbrock-v1

Narrative spec for the Phase 3a NLP probe. Not a compiler input.

Phase 3a tests that the class router can run **exchange + residual + local
neighborhood** on an unconstrained smooth problem, without claiming a dual
or SMT certificate.

## Narrative

Minimize the Rosenbrock banana function

\[
f(x, y) = (1 - x)^2 + 100 (y - x^2)^2
\]

Unconstrained. Canonical variables: `x`, `y`. Sense: `min`.

Known minimizer: `(1, 1)` with value `0`. This is a global min of this
function, but dubito's NLP ceiling is only residual feasibility plus a local
neighborhood. The score must not say "LP dual closed".

## Independent formulations

Two SciPy encodings, written separately (Nelder-Mead vs L-BFGS-B). They must
not import the YAML `verification` block. A planted bug that only rescales
the `100` coefficient still has the same minimizer — do **not** use that.
The planted bug shifts the valley: `(2 - x)^2 + 100 (y - x^2)^2`, minimizer
`(2, 4)`.

## What must not live here

A shared residual expression that both SciPy modules compile from.
