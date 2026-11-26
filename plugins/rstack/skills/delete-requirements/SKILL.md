---
name: delete-requirements
description: Remove unnecessary questioned requirements, custom code, and process steps, adopt proven open-source replacements, implement empirically validated performance optimizations on surviving parts, encode surviving requirements in code and data, and prove engineer intent and non-regression.
---

# Delete requirements

Act on a questioned requirements dossier (`R1`, `R2`, …) to shrink footprint,
simplify the design, optimize what remains, and prove nothing important broke.
Works on a **plan**, an **implemented feature or section of the codebase**, or
a **workflow**.

Follow the strict order: **delete first, optimize second, prove everything.**
Never optimize a component or workflow step that should be deleted.

## 1. Delete unnecessary requirements, code, and process

For each challenged requirement (`R#`):

- **Verify against engineer intent:** Confirm deleting the requirement,
  component, abstraction, fallback, or process step does **not** violate
  engineer intent or an unwaivable safety, security, or release gate.
- **Delete aggressively:**
  - On a **plan:** Remove eliminated requirements and components, merge
    unnecessary layers, replace custom parts with adopted OSS tools, split
    serial edges into parallel workstreams, and invoke `scope-work` to update
    the plan's clock-time estimates.
  - On an **implemented feature or section of the codebase:** Delete
    dead/redundant code, abstractions, custom reimplementations replaced by
    adopted OSS, and stale prose/comments. Keep glue thin.
  - On a **workflow or dev cycle:** Delete redundant checks, serial
    bottlenecks, cold-build paths, or unnecessary manual steps.
- **Keep with evidence:** If a questioned requirement survives (deleting it
  would break intent or an active gate), record the exact reason it stayed.

## 2. Optimize surviving parts (only after deletion)

Take proven performance headroom opportunities (FPS, latency, RAM, throughput,
compile/test/CI duration) that still apply to surviving components:

1. Implement the optimization cleanly against the simplified architecture.
2. Vet every before/after measurement with **`benchmark-checklist`** when
   installed (limiter, production tuning, arithmetic limits, error count,
   repeatability within budget, end-to-end impact, and proof the work actually
   ran).
3. Reject any optimization that regresses a surviving requirement, adds
   disproportionate maintenance complexity, or fails benchmark vetting.

## 3. Prove intent and non-regression

Deleting requirements is never done on faith. Run the applicable verification
workflow before accepting the result:

- **Project verification:** Invoke the repository's verification skill
  (`verify-*`, if installed) and its canonical build, test, and lint checks to
  prove engineer intent and every surviving requirement still pass.
- **Benchmark verification:** Confirm optimizations improved the real metric
  without hidden errors or unmeasured regressions.

If deleting a requirement broke intent (the healthy ~10% add-back rate),
restore only the minimal piece required and encode a test proving why it
exists.

## 4. Encode surviving requirements in code and data (not drifting Markdown)

For every requirement, invariant, and metric that survived deletion:

- **Express it in code or deterministic data:** Use strong types, state enums,
  runtime assertions, schema validators, executable unit/integration tests, or
  structured JSON/JSONL metric baselines — not parallel prose Markdown docs or
  explanatory comments that drift out of date.
- **Delete stale docs and comments** that described deleted parts or duplicate
  what the code now states directly.
- **Leave clean git history:** In the commit message and PR description, name
  the exact requirements deleted, OSS adopted, optimizations proven, and
  verification receipts so future readers can inspect `git log -p` / `git diff`
  to understand design decisions over time.
