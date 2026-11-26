---
name: status-report
description: Reconcile an active plan or goal with what landed, what is implemented and awaiting merge, blockers requiring human action, and remaining tasks. Uses scope-work for empirical clock-time estimates and groups active requirements by the plan's component sections.
---

# Status report

## Establish scope and evidence

- Start with the plan or goal the user names; otherwise use the active goal and
  latest accepted plan in context, docs, or tracker. Identify the scope and
  relevant repositories, following cross-repo dependencies.
- Reconcile plan tasks against source-of-truth evidence: remote branches, PR
  history, current CI checks, reviews, merge status, and local worktree state.
- Map evidence so multiple PRs for one task never inflate progress. Keep
  downstream certification, releases, or integration tracked separately until
  verified on their intended target.
- Gather evidence read-only for the report.

## Estimate plan progress by effort

- Estimate active work time per in-scope task in a common unit (such as work
  hours), split into verified completed effort and remaining effort.
- Calculate **100 × completed effort ÷ (completed effort + remaining effort)**.
  Count each piece once; exclude idle queue or human approval waits from effort.
- State the basis in one line (or headline **Progress estimate unavailable** and
  name what is missing).

## Size remaining work using `scope-work`

Always invoke **`scope-work`** to size remaining `implementation` requirements
and derive clock times. Do not invent ad-hoc estimates or bypass `scope-work`:

1. Feed every unstarted requirement, remaining portion of in-progress work, and
   newly discovered work into `scope-work`. When new work is found, add it to
   the plan and percentage in the same report and name what was added.
2. Follow `scope-work`'s phase-by-phase breakdown (`edit`, `build_test`,
   `verify` with `min` + `why` from shared `scope_model.rates`) and
   `depends_on` graph so parallel lanes are never double-counted in clock time.
3. **Pass through `scope-work`'s full derivations verbatim into the report:**
   include both clock-time numbers (first-pass and failure-adjusted), the
   critical-path ID chain, historical reference class, failure multiplier,
   confidence level, and key risks.
4. Keep waits on a person (`human_gates`) out of both clock-time numbers and
   list them under **Human action needed**.

## Present in requirements format grouped by component sections

Group active requirements, blockers, gates, assumptions, and remaining
implementation work under the **same architecture component sections** used by
the plan's requirements register (using stable global IDs `R1`, `R2`, … and the
four statuses `needs-you`, `user-specified`, `validated`, `unconfirmed`) so
every item can be inspected, questioned, or updated directly in the register.

| ID | Section | Story / requirement | Status | Backing evidence or `scope-work` derivation |
| --- | --- | --- | --- | --- |

## Write the report

Lead with **<plan or goal> — ~<percent>% complete by effort**, a one-sentence
plain goal summary, the estimate basis, and the critical-path first-pass and
failure-adjusted clock times from `scope-work`. Use short, direct sentences and
one compact bullet per task.

Then include:

### Landed

Verified work by section/requirement (`R#`) and repository with merged PR or
target-branch commit links.

### Implemented and awaiting merge

Each PR or local branch with repository, current state, specific blocker or
next gate (referencing its `R#` ID and section), and next action.

### Human action needed

Decisions, approvals, access, or hardware a person must provide (referencing
their `R#` IDs and sections), naming who owns each action and what it unlocks.
Say "None identified" when none exist.

### Remaining work

Outstanding `implementation` requirements grouped by component section
(referencing `R#` IDs), carrying through first-pass and failure-adjusted clock
times, phase breakdown / rate basis, `depends_on` edges, and material risks.
