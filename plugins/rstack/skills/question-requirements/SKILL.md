---
name: question-requirements
description: "Spawn a fresh subagent to challenge either the premise or the scoped work of any requirement (R1, R2, ...), including user-specified decisions. Performs deep web research for open-source replacements, runs minimal empirical spikes in isolated directories or worktrees, and challenges phase breakdowns, rates, and depends_on edges."
---

# Question requirements

Challenge **either the premise/content of any requirement, or the scoped work of
any requirement** (`R1`, `R2`, …) with empirical evidence instead of opinion.
Works on **any** requirements register — a plan, an implemented feature or
section of the codebase, a status report, or a workflow.

**Primary goal:** Minimize the total amount of code and process the project
must implement and maintain while preserving engineer intent.

## Mandatory rule: always run in a fresh subagent

You **must** execute the interrogation inside a **fresh subagent with zero
prior conversation context** (using the host's subagent / delegation tool). Do
not question requirements inside the same context that authored them.

Pass the fresh subagent **only**:

1. The requirements register JSON (`R1`, `R2`, … grouped by component section)
   and any accompanying diagrams or target reference (plan text, repository
   path + commit/diff + `git log -p` access, status report, or workflow
   report).
2. This skill (`question-requirements`) and `benchmark-checklist` (when
   installed).

## Keep the target untouched; run minimal spikes in isolation

- **Never modify** the active branch, working checkout, or source plan.
- **Do run empirical spikes** in disposable scratch directories (`/tmp/...`) or
  a **disposable git worktree** when you need to build or test against the real
  project. Inside that disposable worktree, you may edit code on the real
  project in a targeted way purely to prove or disprove a requirement,
  infeasibility, or performance ceiling.
- **Keep every spike as small as possible:** The goal is empirical proof, not
  writing final production code. Capture the exact command and measured output,
  then remove the disposable worktree or scratch directory when done.

## What the fresh subagent must interrogate

Walk every `R#` systematically across both **premise** and **scope**:

### 1. Question the premise of any requirement (no exemptions)

- **No requirement is exempt — including `user-specified` ones:** Question
  user-explicit decisions whenever evidence shows a better or simpler path or
  shows the decision does not apply. Keep the **product outcomes** the engineer
  stated; challenge the **means**.
- **Overriding an engineer decision:** When empirical evidence overrides a
  `user-specified` decision, nominate the replacement, set the proposed status
  to **`needs-you`**, and explicitly write **`overrides your decision`** with
  the evidence so the engineer can review or veto it.
- **Deep web research for open-source and existing tools:** For every
  requirement implying custom code, a bespoke library, protocol, script,
  service, or workflow:
  1. State the underlying need in one plain sentence without naming the
     proposed custom solution.
  2. Audit what is already in the project's stack (current docs, installed
     versions, license tiers — never memory).
  3. Run deep web research across problem-domain terms, GitHub repositories
     (READMEs, architecture, recency, issues, actual source files), package
     registries (`crates.io`, `npm`, `PyPI`, system packages, platform SDKs),
     engineering blogs, RFCs, and hosted services. Prefer choices that minimize
     long-term maintenance and unlock future features — even if adopting
     requires reshaping the design to fit the tool.
  4. Record queries run, candidate URLs, adoption path (as-is, configured, or
     small glue), license, and maintenance delta. If glue grows beyond a small
     script, search again.
  5. **Keeping custom code requires empirical disproof:** For every ruled-out
     candidate, name the exact surviving requirement it fails and prove it with
     a link, file/line, or minimal spike. *"It does not fit our current
     design"* is not evidence. Custom work without this research record is a
     review blocker.
- **Delete every part that does not earn its keep:** Challenge "in case"
  hedges, abstractions, fallbacks, config knobs, and our own conventions that
  force custom code. Apply the 10% test: if you did not find requirements worth
  deleting, you have not questioned hard enough.
- **Empirically spike infeasibilities, risks, and performance metrics:**
  - Never accept `UNVERIFIED_INFEASIBILITY`, "unsupported", or "too risky" at
    face value — run the smallest targeted spike to produce
    `CONFIRMED_INFEASIBLE`, `DISPROVED`, or `BLOCKED`.
  - For performance, timing, or resource requirements, ask whether we can do
    better (higher FPS, lower RAM/latency, faster builds/CI) and vet spike
    numbers with **`benchmark-checklist`** when installed.
  - Flag any `user-specified` requirement that hides an untested technical
    assumption and nominate splitting the untested part into its own
    `unconfirmed` requirement.

### 2. Question the scope of any implementation requirement

For every `implementation` requirement (as part of questioning that
requirement, never as a separate scope table):

- Challenge **`scope.first_pass_min`** and the arithmetic in each phase's
  **`breakdown` (`edit`, `build_test`, `verify`)**: are the LOC counts, cycle
  counts, and `why` justifications grounded in reality?
- Challenge the shared **`scope_model.rates`** and **`failure_multiplier`**:
  are assumed rates too optimistic or inflated, and can a quick spike calibrate
  them?
- Challenge every **`scope.depends_on`** edge: is it a true data/contract
  dependency or accidental serialization that can run in parallel?
- Challenge whether simplifying or adopting OSS shrinks or removes the work
  altogether.

## Output format

Return a compact, evidence-backed dossier referencing **`R#` + component
section** — do not split requirements into separate category sections. Every
finding must state whether it challenges **`premise`** or **`scope`**, the
evidence, and the proposed new value (or deletion):

1. **Summary:** Overall verdict, estimated code/process footprint or time
   removable, and top invalidated assumptions.
2. **Requirements you can delete or change:** Each `R#` (`section`) with
   `premise` or `scope` tag, concrete evidence (search queries & candidate
   URLs, minimal spike command & measured output, arithmetic/dependency proof,
   or impact if removed), and the exact proposed deletion, replacement,
   status (`needs-you` + `"overrides your decision"` when overriding the
   engineer), or new `scope` values / `depends_on` edges.
3. **Requirements you validated:** Each `R#` (`section`) that withstood
   interrogation (both premise and scope), with the empirical evidence or
   disproof showing why it stays (including any vetted performance headroom
   found on surviving requirements).
