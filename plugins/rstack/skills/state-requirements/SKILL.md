---
name: state-requirements
description: "Author and render a validated JSON requirements register grouped by architecture component sections, with one-line user stories, four explicit statuses, assumption vs implementation kinds, phase-by-phase scope on implementation requirements, and an interactive self-contained HTML view."
---

# State requirements

Make every implicit requirement motivating a plan, an implemented feature or
section of the codebase, or a workflow explicit and empirically testable. A
**requirement** is anything that motivates a decision: user intent,
architecture choices, owned code footprint, assumptions, performance or timing
metrics, stated infeasibilities, risks, and implementation work.

Store the register as a **JSON file** (the source of truth) and render it with
the bundled stdlib script into **one self-contained HTML view** — never dump a
giant flat 50-row Markdown table in chat.

## Grounding rule: code and data over prose

- **On an implemented feature or section of the codebase:** Derive requirements
  from source code, types, state enums, runtime assertions, tests, build
  configs, recorded metrics, and `git log -p` / `git diff`. Never trust a
  Markdown doc or comment over code. Flag any requirement that lives only in
  prose or comments as encoding debt.
- **On a plan:** Extract every decision and assumption implied by the plan.
- **On a workflow or dev cycle:** Extract every stage, wait, check, failure
  mode, and timing bottleneck from measured data.
- **Future intentions:** When documenting long-term maintenance and
  extensibility for a feature, **if the user has not expressed future
  intentions, ask the user for explanations instead of assuming.**
- **No permanent drifting prose docs:** Do not maintain a parallel hand-edited
  Markdown requirements spec for implemented code; surviving requirements
  belong encoded directly in code, tests, and structured data.

## Step 1: Diagrams (prerequisite)

If current diagrams have not been generated yet for the target, invoke
**`system-diagram`** first:

- For a plan or system, build **one top-level `architecture` diagram** (its
  component IDs become the section IDs of the requirements register), plus
  **`flow` diagrams only for critical paths**.
- For a lifecycle or workflow, build a **`flow` diagram**.
- Ensure all known or targeted performance and timing metrics appear on nodes
  and edges.

## Step 2: Author the JSON requirements register

Use **one simple global sequential ID system (`R1`, `R2`, `R3`, …)** across all
sections — never per-section ID prefixes. Group requirements into **sections**
matching the architecture diagram's component IDs (plus `intent` and `cross`
meta sections as needed), each with a one-sentence `summary`.

### Required schema per requirement

- `id`: global, stable (`R1`, `R2`, …; revisions may carry primes such as
  `R18'` if tracking edits).
- `story`: **the headline — one line, about 12 words or fewer**, describing
  what someone experiences (a user, an agent using the product, or an agent
  building/operating it). Technical detail goes in `text`, never in `story`.
- `text`: the technical statement.
- `backing`: concrete evidence (measured receipt, doc/code pointer, LOC
  footprint, spike result, or `USER`).
- `states`: referenced state or component IDs from the diagram (or `—`).
- `category`: short tag (`intent`, `arch`, `perf`, `security`, `ops`, etc.).
- `status`: **exactly one of four statuses** (precedence `needs-you` >
  `user-specified` > `validated` > `unconfirmed`):
  - `needs-you`: a decision only the engineer can make, including any place
    where evidence overrode an engineer decision.
  - `user-specified`: stated by the engineer (records source, **not**
    evidence). **Never let `user-specified` hide risk:** if a user-specified
    requirement depends on an untested technical part, split that untested part
    into its own `unconfirmed` requirement.
  - `validated`: measured, spiked, or confirmed by docs or source.
  - `unconfirmed`: assumed, unmeasured, or untested (including
    `UNVERIFIED_INFEASIBILITY` claims).
- `kind`: **exactly one of two kinds**:
  - `assumption`: informs design and is not work (intent, constraints,
    budgets, infeasibility claims, invariants). **Must carry no `scope`.**
  - `implementation`: something you actually build. **Must carry full `scope`**
    when proposing new work (no standalone scope or parallelism requirements!).
- `scope` (`implementation` requirements only): invoke **`scope-work`** to
  populate `first_pass_min`, `depends_on`, `breakdown` (`edit`, `build_test`,
  `verify` with `min` + `why`), `basis`, and `risk`, plus top-level
  `scope_model` (`rates`, `failure_multiplier`, `reference`, `confidence`,
  `human_gates`). Totals and the critical path are **derived by the renderer**.
- Optional: `short` (compact label for the chat attention summary) and `change`
  (`added` | `changed` | `deleted` for round-delta filtering).

*Note on existing code:* When analyzing an already-implemented feature or
section of the codebase (no new work proposed), requirements are `assumption`
rows describing what the code enforces today (no `scope` required).

## Step 3: Validate and render the inline view

Run the bundled renderer and validator:

```sh
python3 PATH_TO_THIS_SKILL/scripts/render_register.py register.json \
  --out /tmp/register.html [--arch arch.json] [--max-height 720]

# Print the concise plain-text attention summary for chat
python3 PATH_TO_THIS_SKILL/scripts/render_register.py register.json --summary
```

The validator refuses missing stories, unknown statuses/kinds/changes,
duplicate IDs, missing or non-summing implementation scopes, scope on
assumptions, non-implementation `depends_on`, dependency cycles, and (with
`--arch`) section IDs not matching architecture component IDs.

## Display rule

- If the host can display HTML inline, show the rendered HTML register inline;
  otherwise save the file and link it.
- In chat, **always** accompany the view with the short plain-text attention
  summary (`--summary`): `Needs you` items plus any `unconfirmed` items on the
  critical path.
