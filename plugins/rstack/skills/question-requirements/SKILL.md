---
name: question-requirements
description: Spawn a fresh subagent to challenge every stated requirement (R1, R2, ...), perform deep web research for open-source or existing tools that replace custom code, run minimal empirical spikes in isolated directories or worktrees on claimed infeasibilities and performance ceilings, and challenge parallelism and scoped estimates.
---

# Question requirements

Challenge every stated requirement (`R1`, `R2`, …) with empirical evidence
instead of opinion. Works on **any** requirements set — a plan, an implemented
feature or section of the codebase, a status report, or a workflow.

**Primary goal:** Minimize the total amount of code and process the project
must implement and maintain while preserving engineer intent.

## Mandatory rule: always run in a fresh subagent

You **must** execute the interrogation inside a **fresh subagent with zero
prior conversation context** (using the host's subagent / delegation tool). Do
not question requirements inside the same context that authored them.

Pass the fresh subagent **only**:

1. The stated requirements set (`R1`, `R2`, …) and any accompanying diagram or
   target reference (plan text, repository path + commit/diff + `git log -p`
   access, status report, or workflow report).
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

Walk every `R#` systematically:

### 1. Deep web research for open-source and existing tools

For every requirement that implies custom code, a bespoke library, protocol,
script, service, or workflow:

1. **State the underlying need** in one plain sentence without naming the
   proposed custom solution.
2. **Audit what is already in the project's stack:** Read current docs,
   installed versions, and license tiers of tools/services already in use
   (never rely on memory).
3. **Run deep web research** to find open-source projects, libraries, CLI tools,
   or hosted services that eliminate custom implementation:
   - Search multiple angles (problem domain terms, protocol/standard names,
     language ecosystem idioms — not just internal project jargon).
   - Inspect **GitHub repositories** directly (READMEs, architecture,
     stars/recency, issues, maintenance status, and actual source files when
     checking a claimed limitation).
   - Search **package registries and ecosystems** (`crates.io`, `npm`, `PyPI`,
     system package managers, platform SDKs) as well as engineering blogs,
     RFCs, and benchmark writeups.
   - Prefer solutions that minimize long-term maintenance and unlock future
     features around the corner — even if adopting requires short-term
     integration effort or reshaping the design to fit the tool.
4. **Record every candidate** with exact queries run, URLs, adoption path
   (as-is, configured, or small glue), license, and maintenance delta. If glue
   grows beyond a small script, search again.
5. **Keeping custom code requires empirical disproof:** Adopting needs no
   defense; keeping custom code does. For every ruled-out candidate, name the
   exact surviving requirement it fails and prove it with a link, file/line, or
   minimal spike. *"It does not fit our current design"* is not evidence.
   Custom implementation without this research record is a review blocker.

### 2. Nominate requirements and parts for deletion

For every `R#`:

- Who or what actually requires it — true engineer intent, or an "in case"
  hedge?
- What concretely breaks if we delete this requirement, component, abstraction,
  config knob, fallback, or check outright?
- Does one of our own repo conventions or rules force custom work? If so,
  nominate that rule itself for deletion or narrowing.
- Apply the 10% test: if you did not find requirements worth deleting, you have
  not questioned hard enough.

### 3. Empirically spike stated infeasibilities and risks

For every requirement tagged `UNVERIFIED_INFEASIBILITY` or driven by a major
risk:

- Do **not** take "infeasible", "unsupported", or "too risky" at face value.
- Run the smallest possible targeted spike (in `/tmp/...` or a disposable git
  worktree of the real project) to confirm whether the limitation is real.
- Record verdict: `CONFIRMED_INFEASIBLE`, `DISPROVED` (with working spike
  command and output), or `BLOCKED` (naming the exact missing prerequisite or
  hardware).

### 4. Challenge every performance, timing, and resource requirement

For every metric-backed or metric-assuming `R#` (FPS, latency, RAM, throughput,
compile/test/CI duration, etc.):

- Ask whether the metric is actually as good as it can be (higher FPS, lower
  RAM/latency, smaller footprint, faster warm build or CI).
- Run minimal profiling or performance spikes and vet every measurement with
  **`benchmark-checklist`** when installed (limiter, production tuning,
  arithmetic limits, error count, work happened, end-to-end share).

### 5. Challenge parallelism and scoped estimates

- **Parallelism:** For every serial edge (`A -> B`), prove whether it is a true
  data/state dependency or accidental serialization (shared dir, sequential
  script, over-broad lock, serial checks/steps) and propose concrete parallel
  splits.
- **Scoped estimates:** Inspect the historical reference tasks and formulas
  backing every time estimate — challenge both what can be cut from scope and
  whether a faster delivery or verification path exists.

## Output format

Return a compact, evidence-backed dossier referencing exact `R#` IDs — do not
split requirements into separate category sections:

1. **Summary:** Overall verdict, estimated code/process footprint removable,
   and top invalidated assumptions.
2. **Requirements you can delete:** Each `R#` nominated for deletion,
   replacement by an adopted open-source tool, simplification, parallelization,
   or scope reduction, with its concrete evidence (search queries & candidate
   URLs, minimal spike command & measured output, or impact if removed).
3. **Requirements you validated:** Each `R#` that withstood interrogation, with
   the empirical evidence or disproof showing why it stays (including any vetted
   performance headroom found on surviving requirements).
