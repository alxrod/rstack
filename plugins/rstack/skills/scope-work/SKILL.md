---
name: scope-work
description: Derive empirical, explicitly justified clock-time and complexity estimates for proposed work from measured historical dev-cycle data, breaking tasks into 10-60 minute dependency-linked units with first-pass and failure-adjusted clock times.
---

# Scope work

Estimate how long proposed work will actually take to implement, verify,
review, and land — using **measured historical dev-cycle data**, never
instinct. State every derivation explicitly (reference tasks/PRs, phase
durations, failure rate, and assumptions) so any reader can inspect and verify
the estimate.

## 1. Gather empirical baselines via `measure-dev-cycle`

Use **`measure-dev-cycle`** to pull measured historical timings for the target
repository (`analyze --repo OWNER/REPO --since 60d`). If local history for the
repository is empty or stale, collect recent merged PRs first via
`measure-dev-cycle` (`collect --apply --repo OWNER/REPO --since 60d --limit 50`).

Record the empirical baseline metrics used:

- Comparable historical PRs/tasks (repo, subsystem, verification tier, diff
  footprint)
- Measured median (`p50`) and tail (`p90`) duration per phase (`edit`,
  `compile`, `test`, `ci_queue`, `ci_run`, `review`, `merge`)
- Measured first-pass failure / CI rerun rate (`failure_rate`) and average
  retry penalty

## 2. Decompose into dependency-linked work pieces

- Break proposed work into concrete pieces sized between **10 and 60 minutes**
  of active work. Split any item above 2 hours before estimating.
- If a piece cannot be sized because its source or plan has not been inspected,
  write `not sized yet` instead of inventing a number.
- Map explicit dependencies (`A -> B`) and parallel lanes so parallel work is
  **never** double-counted in clock time.
- Separate **human waits** (approvals, design calls, hardware access) from
  automated/agent execution time; list human gates separately.

## 3. Derive two clock-time numbers explicitly

For every work piece and for the full dependency graph (along the critical
path), compute:

1. **First-pass clock time:** Expected wall-clock time along the critical path
   if every build, check, and review passes on the first attempt.
2. **Failure-adjusted clock time:** Expected wall-clock time applying the
   measured historical failure/rerun rate and retry cost from the comparable
   reference class.

Never report only the first-pass number, and never report summed agent-hours as
wall-clock time.

## 4. Emit the explicit derivation table

Present every estimate with its full empirical derivation:

| ID | Work piece | Depends on | Reference class (historical PRs/tasks) | Phase breakdown (edit / build / verify / CI / merge) | First-pass clock | Failure-adjusted clock (rate) | Confidence & assumptions |
| --- | --- | --- | --- | --- | --- | --- | --- |

Include totals:

- **Critical-path first-pass clock time** (naming the critical-path chain)
- **Critical-path failure-adjusted clock time** (stating the exact failure rate
  and retry penalty used)
- **Human waits excluded** (named gates)

## 5. Handle greenfield / thin-data areas honestly

When no close historical reference class exists (new language, new hardware,
new stack):

1. Mark the item `LOW_DATA_CONFIDENCE`.
2. Anchor on the nearest available verification tier (for example portable unit
   tests vs full integration CI vs hardware/staging proof) and state the
   uncertainty range explicitly.
3. Recommend an empirical time-boxed spike to measure the real compile/test/loop
   cost before committing to a large schedule.
4. Once executed, record the actuals with `measure-dev-cycle` so future scoping
   for that area becomes empirical.
