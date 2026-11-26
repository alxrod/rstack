---
name: auto-plan
description: Opt-in autonomous planning and implementation loop. Only run when explicitly triggered by the engineer: creates an unconstrained plan, then loops through state-requirements, question-requirements (fresh subagent), and delete-requirements until two consecutive rounds make no requirement changes, then implements and verifies the plan.
---

# Auto plan

**Opt-in only.** Standard interactive work lets the engineer decide which
requirement skill to run next. Run `auto-plan` **only** when the engineer
explicitly invokes `/auto-plan` (or explicitly asks for an autonomous
plan-refine-implement loop).

## Workflow

1. **Unconstrained initial plan:** Write a raw, unconstrained initial plan for
   the requested goal, including a `state-machine-diagram` that captures its
   states, transitions, failure/recovery paths, and performance/timing metrics.
   Do not artificially limit creativity during initial planning.
2. **State requirements:** Invoke `state-requirements` on the plan (including
   `scope-work` since this proposes new work). Record the resulting unified
   requirements set (`R1`, `R2`, …).
3. **Question requirements (fresh subagent):** Invoke `question-requirements`
   in a fresh subagent with zero prior conversation context to challenge every
   requirement, search deeply for open-source replacements, run minimal
   empirical spikes in isolated directories or worktrees, and challenge
   parallelism and scope.
4. **Delete requirements:** Invoke `delete-requirements` on the plan to remove
   unnecessary requirements, adopt proven open-source tools, simplify the
   architecture, and update scope.
5. **Convergence check (2 unchanged rounds):** Compare the surviving
   requirements set after step 4 against the set entering step 2:
   - If any requirement was added, deleted, replaced by an adopted tool, or
     materially narrowed/changed, reset the unchanged-round counter to `0` and
     repeat steps 2–4 on the updated plan.
   - If **no requirements changed**, increment the unchanged-round counter.
   - Stop looping once **2 consecutive rounds** produce zero requirement
     changes.
   - Guardrail: if 6 rounds complete without convergence, stop and surface the
     oscillating requirements to the engineer instead of looping indefinitely.
6. **Implement and verify:** Once converged, automatically implement the
   finalized plan, encode surviving requirements directly in code, tests, and
   structured data, and verify the result using the repository's verification
   skill (`verify-*`, if installed) or canonical checks (plus
   `benchmark-checklist` when performance or resource targets are part of the
   plan).

## Report

Summarize the converged requirements set, how many rounds it took to converge,
the major requirements deleted or replaced with open-source tools across rounds,
what was implemented, and the verification evidence.
