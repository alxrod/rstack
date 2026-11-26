---
name: delete-requirements
description: "Apply premise deletions, OSS replacements, and scope/dependency edits directly to the requirements register (never maintaining a separate scope table), implement empirically validated optimizations on surviving parts, encode surviving requirements in code and data, and prove engineer intent and non-regression."
---

# Delete requirements

Act on a questioned requirements dossier (`R1`, `R2`, …) to shrink footprint,
simplify the design, tighten scope, optimize what remains, and prove nothing
important broke. Works on a **plan**, an **implemented feature or section of
the codebase**, or a **workflow**.

Follow the strict order: **delete first, optimize second, prove everything.**
Never optimize a component or workflow step that should be deleted.

## 1. Apply premise and scope findings directly to the register

For each challenged requirement (`R#`):

- **Verify against engineer intent:** Confirm deleting a requirement,
  component, abstraction, fallback, or process step does **not** violate the
  product outcomes the engineer wants or an unwaivable safety, security, or
  release gate.
- **When evidence overrides a `user-specified` decision:** Apply the
  evidence-backed change, set `status` to **`needs-you`**, and state
  **`overrides your decision`** with the evidence in `backing` (and `short`) so
  the engineer can review or veto it immediately.
- **Delete aggressively:**
  - On a **plan / JSON register:** Remove eliminated requirements and
    components (or mark `change: "deleted"` for one round when producing a
    round delta), replace custom parts with adopted OSS tools, split hidden
    untested risks out of `user-specified` rows into their own `unconfirmed`
    requirements, and update `story` / `text` / `backing` / `status`.
  - **Apply scope findings directly on the requirement:** Edit that
    implementation requirement's `scope` (`first_pass_min`, `breakdown` phases
    and `why`, `depends_on`, `basis`, `risk`) and shared `scope_model.rates`
    via **`scope-work`** when needed, then re-render the register so totals and
    the critical path are **always re-derived automatically**. Never maintain a
    separate scope table or standalone scope/parallelism requirements.
  - On an **implemented feature or section of the codebase:** Delete
    dead/redundant code, abstractions, custom reimplementations replaced by
    adopted OSS, and stale prose/comments. Keep glue thin.
  - On a **workflow or dev cycle:** Delete redundant checks, serial
    bottlenecks, cold-build paths, or unnecessary manual steps.
- **Track round deltas when iterating:** Set `change` to `added`, `changed`, or
  `deleted` on requirements modified in the current pass so the rendered view's
  `Changed this round` filter highlights only what moved.
- **Keep with evidence:** If a questioned requirement survives, update its
  `status` (`validated` when proved) and record the exact evidence in
  `backing`.

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
