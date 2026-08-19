"""Backend adapters are imported from their modules, never as a bundle.

CVXPY (via optional highspy) and OR-Tools ship incompatible HiGHS libraries.
Importing both in one process can fail. Callers that need both should use
`dubito.sandbox` so each formulation runs in its own interpreter.
"""
