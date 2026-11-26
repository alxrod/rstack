---
name: auto-plan
description: "Opt-in autonomous planning and implementation loop. Only run when explicitly triggered by the engineer: creates an unconstrained plan with architecture/flow diagrams and a JSON register, loops state-requirements, question-requirements (fresh subagent), and delete-requirements with rendered round views and deltas until two consecutive rounds make no material requirement changes, then implements and verifies."
---

# Auto plan

**Opt-in only.** Standard interactive work lets the engineer decide which
requirement skill to run next. Run `auto-plan` **only** when the engineer
explicitly invokes `/auto-plan` (or explicitly asks for an autonomous
plan-refine-implement loop).

## Workflow

1. **Unconstrained initial plan & diagrams:** Write a raw, unconstrained
   initial plan for the requested goal. Use **`system-diagram`** to render one
   top-level **`architecture`** diagram (components, boundaries, protocols,
   edge metrics) plus **`flow`** diagrams only for the critical paths. Do not
   artificially limit creativity during initial planning.
2. **State requirements (JSON register + rendered view):** Invoke
   **`state-requirements`** to author the JSON requirements register (sections
   matching the architecture component IDs, `assumption` vs `implementation`
   kinds, phase-by-phase `scope` via `scope-work` on every implementation
   requirement). Validate with `render_register.py --arch <arch.json>` and
   render the self-contained HTML register view.
3. **Question requirements (fresh subagent):** Invoke **`question-requirements`**
   in a fresh subagent with zero prior conversation context to challenge either
   the **premise** or the **scope** of every requirement (including
   `user-specified` decisions), run deep web OSS research, and run minimal
   targeted spikes in disposable directories or worktrees.
4. **Delete & update requirements (with round deltas):** Invoke
   **`delete-requirements`** to apply premise deletions, OSS replacements,
   engineer-decision overrides (`status: "needs-you"` + `"overrides your
   decision"`), and per-requirement `scope` / `depends_on` edits directly in
   the register JSON. Tag requirements touched in this round with
   `change: "added" | "changed" | "deleted"` (clearing previous round's
   `deleted` rows and `change` flags before starting each new round).
5. **Per-round presentation (no giant Markdown tables):** After each round:
   - Re-render updated diagrams through `system-diagram`'s script and
     re-render the register through `render_register.py --arch <arch.json>`.
   - Show the rendered HTML inline if the host supports it, otherwise save and
     link the files.
   - Post only the concise plain-text attention summary
     (`render_register.py --summary`: `Needs you`, `unconfirmed` on the
     critical path, scope totals, and round delta counts). Never dump a 50-row
     raw Markdown table in chat.
6. **Material-change convergence check (2 unchanged rounds):** Compare the
   surviving register after step 4 against the register entering step 2:
   - **Material change** (resets unchanged-round counter to `0`): adding or
     deleting a requirement, changing architecture or OSS adoption, flipping an
     infeasibility/risk verdict or overriding a user decision, or changing an
     implementation requirement's `scope.first_pass_min` or `scope.depends_on`
     edges.
   - **Non-material polish** (does **not** reset convergence): small late-round
     correctness or edge-case guard tweaks (~15 LOC details that unit tests
     already in the plan would catch). Apply them cleanly, note them as
     non-material polish, and still count the round as materially unchanged so
     the loop does not spin indefinitely.
   - Stop looping once **2 consecutive rounds** produce zero **material**
     requirement changes.
   - Guardrail: if 6 rounds complete without convergence, stop and surface the
     oscillating requirements explicitly.
7. **Check `needs-you` gates, then implement and verify:** If any `needs-you`
   items require an engineer decision or veto (including `"overrides your
   decision"` rows), surface them clearly before mutating code when a wrong
   choice would waste significant work; otherwise implement the finalized plan,
   encode surviving requirements directly in code, tests, and structured data,
   and verify using the repository's verification skill (`verify-*`, if
   installed) or canonical checks (plus `benchmark-checklist` when performance
   targets exist).

## Report

Present the final rendered architecture/flow diagrams, the final rendered
register HTML view (or file link), the `--summary` attention block, how many
rounds it took to reach material convergence (noting any non-material late
polish), the major requirements deleted or replaced with OSS tools, what was
implemented, and the verification evidence.
