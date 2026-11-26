---
name: status-report
description: Reconcile an active plan or goal with what landed, what is implemented and awaiting merge, blockers requiring human action, and remaining tasks. Uses scope-work for empirical clock-time estimates and presents active scope, blockers, assumptions, and estimates in requirements format.
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

Always invoke **`scope-work`** to size remaining work and derive clock times.
Do not invent ad-hoc estimates or bypass `scope-work`:

1. Feed every unstarted task, remaining portion of in-progress work, and newly
   discovered work into `scope-work`. When new work is found, add it to the
   plan and percentage in the same report and name what was added.
2. Follow `scope-work`'s 10–60 minute piece sizing (splitting items above 2
   hours, writing `not sized yet` when source/plan has not been read) and
   dependency graph so parallel lanes are never double-counted in clock time.
3. **Pass through `scope-work`'s full derivations verbatim into the report:**
   include both clock-time numbers (first-pass and failure-adjusted), the exact
   historical reference tasks/PRs, phase breakdown, failure rate, retry penalty,
   confidence level, and assumptions for every item and the critical path.
4. Keep waits on a person out of both clock-time numbers and list them under
   **Human action needed**.

## Present in requirements format

Express the active plan's scope, dependencies, blockers, gates, assumptions,
and scoped clock-time estimates as explicit, uniquely numbered **requirements**
(`R1`, `R2`, …) with their backing evidence or `scope-work` derivations — so
every assumption, dependency, blocker, or estimate in the status report can be
inspected, challenged, or deleted directly without rewriting the report.

| ID | Category | Requirement / current assumption | Backing evidence or `scope-work` derivation | Status |
| --- | --- | --- | --- | --- |

## Write the report

Lead with **<plan or goal> — ~<percent>% complete by effort**, a one-sentence
plain goal summary, the estimate basis, and the critical-path first-pass and
failure-adjusted clock times from `scope-work`. Use short, direct sentences and
one compact bullet per task.

Then include:

### Landed

Verified work by task and repository with merged PR or target-branch commit links.

### Implemented and awaiting merge

Each PR or local branch with repository, current state, specific blocker or next
gate (referencing its `R#` ID), and next action.

### Human action needed

Decisions, approvals, access, or hardware a person must provide (referencing
their `R#` IDs), naming who owns each action and what it unlocks. Say "None
identified" when none exist.

### Remaining work

Outstanding tasks broken into `scope-work`'s 10–60 minute pieces (referencing
`R#` IDs), carrying through each group's two clock-time numbers, historical
derivation, dependencies, and material unknowns.
