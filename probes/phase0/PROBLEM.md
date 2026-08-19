# furniture-workshop-v1

Working name of the tool: `dubito` (TBD). This file is the **narrative spec**, not a constraint IR.

Phase 0 uses this single MILP to test the hypothesis:

> Independent formulations of the same narrative, when they disagree under solution exchange, detect formulation bugs.

## Narrative

A small workshop makes tables and chairs.

- One **table** uses **3** units of wood and **2** units of labor, and yields profit **50**.
- One **chair** uses **1** unit of wood and **1** unit of labor, and yields profit **20**.
- The workshop has **12** units of wood and **10** units of labor.
- Marketing requires **at least two chairs for every table** produced.
- Production quantities are non-negative integers.
- The objective is to **maximize** profit.

Canonical variable names (exchange interface only): `tables`, `chairs`.

## Hand enumeration (probe oracle, not part of the checker)

Feasible integer points include `(tables, chairs) = (0, 0..10)`, `(1, 2..8)`, `(2, 4..6)`.
The unique optimum is `tables=2`, `chairs=6`, profit `220`.

## What must not live here

Do not put a single constraint matrix that both backends compile from. Each formulation module re-reads this narrative and writes solver-native code independently. The YAML sibling file lists only variable names, kinds, and bounds so the exchange layer knows the assignment keys.
