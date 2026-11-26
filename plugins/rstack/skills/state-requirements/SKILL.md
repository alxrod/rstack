---
name: state-requirements
description: Exhaustively state every requirement motivating a plan, an implemented feature or section of the codebase, or a workflow. Produces a unified requirements register (with supporting assumptions, code footprint, performance metrics, stated infeasibilities, risks, dependencies, and scope when proposing new work) alongside a state machine diagram.
---

# State requirements

Make every implicit requirement motivating a design, decision, or workflow
explicit and empirically testable. A **requirement** is anything that motivates
a decision: user intent, architecture and owned code footprint, assumptions,
performance or timing metrics, stated infeasibilities, risks, parallelism or
dependency constraints, and scoped work estimates.

Run this on a **plan**, on an **implemented feature or section of the codebase**,
or on a **workflow/dev cycle**. Do not polish or defend the target — expose
everything it assumes with concrete backing evidence.

## Grounding rule: code and data over prose

- **On an implemented feature or section of the codebase:** Derive requirements
  from source code, types, state enums, runtime assertions, tests, build
  configs, recorded metrics, and `git log -p` / `git diff`. Never trust a
  Markdown doc or comment over code. Flag any requirement that lives only in
  prose or comments as encoding debt.
- **On a plan:** Extract every decision and assumption implied by the plan.
- **On a workflow or dev cycle:** Extract every stage, wait, check, failure
  mode, and timing bottleneck from measured data.
- **No permanent drifting docs:** Do not create a hand-maintained requirements
  Markdown file in the repository for implemented code. Keep the register in
  the response or in an ephemeral receipt; surviving requirements belong
  encoded directly in code, tests, and structured data.

## Step 1: State machine diagram (prerequisite)

If a current state machine diagram has not been generated yet for the target,
invoke **`state-machine-diagram`** first to build and validate one (reflecting
all known or targeted performance and timing metrics directly on the states and
transitions). If an up-to-date diagram already exists, reuse and reference its
state IDs below.

## Step 2: Unified requirements register

Express **everything** reported by this skill as conceptual **requirements**
under **one simple sequential ID system (`R1`, `R2`, `R3`, …)** — never split
into separate lettered namespaces. Every requirement carries its category, its
backing explanation (the assumptions, risks, or metrics supporting why it
exists), and whether it is `MEASURED` (with command/receipt) or `ASSUMED`.

| ID | Category | State IDs | Requirement statement | Backing explanation (assumptions, metrics, risks, or footprint) | Source & encoding (`code` / `data` / `prose-only`) |
| --- | --- | --- | --- | --- | --- |

Ensure the unified register explicitly covers every applicable dimension below:

1. **Intent requirements:** The 1 to 3 plain user or product outcomes that the
   work exists to deliver, separated from implementation choices made to serve
   them.
2. **Architecture, stack, and owned code footprint requirements:** Every tech
   stack choice, protocol, external/OSS tool, and custom component (parser,
   daemon, UI surface, script, CI job, glue layer), stating:
   - Whether it is custom or adopted and its exact/estimated owned footprint
     (files, LOC, operational surface).
   - Its long-term maintenance trajectory and extensibility. **If the user has
     not expressed future intentions for a feature, ask the user for
     explanations instead of assuming.**
   - Any inherited repository convention or self-imposed rule that forces extra
     custom work (list it as its own `R#` so it can be examined directly).
3. **Performance, timing, and resource requirements:** Every expectation on UI
   reactiveness, frame rate / FPS, frame pacing, input-to-photon latency,
   network/IPC latency, throughput, RAM/CPU/GPU/disk footprint, startup time,
   or build/test/CI duration — stated as concrete numbers (`MEASURED` with
   receipt/command vs `ASSUMED`), never vague adjectives like "fast" or
   "smooth".
4. **Infeasibility and workaround requirements:** Anything treated as
   infeasible, unsupported, or "designed around", along with the workaround it
   caused. Tag unproven claims `UNVERIFIED_INFEASIBILITY`.
5. **Risk-driven requirements:** Every risk that introduced defensive code,
   indirection, fallbacks, abstractions, or extra process steps, stating the
   footprint it adds.
6. **Parallelism and dependency requirements:** Which tasks, builds, checks, or
   runtime stages are claimed serial vs parallel, naming the exact claimed
   reason for every serial edge (`A -> B`).

## Step 3: Scoped work requirements (new work only)

**Only when proposing new work (such as a plan)** — not when analyzing an
already-implemented feature or section of the codebase — invoke **`scope-work`**
and record its empirically derived task breakdown, first-pass clock time,
failure-adjusted clock time, and explicit derivations as requirements (`R#`) in
the register above.
