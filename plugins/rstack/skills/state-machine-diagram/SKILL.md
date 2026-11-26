---
name: state-machine-diagram
description: Represent any plan, implemented feature, or workflow as both a validated Mermaid stateDiagram-v2 text spec and a clean visual diagram with performance and timing metrics directly reflected on states and transitions. Include a state machine diagram whenever expressing a plan.
---

# State machine diagram

Turn any plan, implemented feature/subsystem, or workflow into a canonical
state machine represented **both in text and visually**. Include a state machine
diagram whenever expressing a plan so every state, transition, guard, failure
path, concurrency region, and performance/timing metric is immediately clear to
the reader.

## Source of truth

- **Plan:** Model every lifecycle stage, component boundary, handoff, failure
  mode, recovery path, and concurrency lane implied by the plan.
- **Implemented feature or section of the codebase:** Derive states and
  transitions directly from actual code (enums, match arms, handlers, configs,
  tests, and `git log -p` / `git diff`). Never copy a stale Markdown doc or
  comment when code disagrees; flag discrepancies.
- **Workflow or dev cycle:** Model every stage, queue, review, retry, and
  completion transition from the measured workflow data.

**Always reflect metrics in the diagram:** In **every** mode (plan, code, or
workflow), annotate states and transitions directly with any known or targeted
performance, timing, latency, throughput, frame-rate, memory, or queue metrics
(for example `WarmBuild [p50 74s, target <= 90s]`, `RenderFrame [120 fps / <= 8.3ms]`,
or `Ready --> Merged : merge (p50 4m)`). Mark assumed targets vs measured
values clearly when both exist.

## Authoring rules (learned from `pstack/statechart`)

1. **Reader's words:** Label states and transitions with what the reader sees
   or cares about, not raw internal variable names.
2. **Clarity budget (~20 arrows or fewer):** Keep diagrams readable. Group
   equivalent sub-states under coarser labels before drawing dozens of noisy
   arrows. Keep every failure/bottleneck path visible, every state reachable
   from `[*]`, and at least one outgoing edge on every non-terminal state.
3. **Complete edges:** Include explicit `[*]` start and terminal/rollback
   states, guards (`[guard]`), actions (`/ action`), failure/retry paths,
   external boundaries (human gates, devices, APIs, CI queues, OSS tools), and
   `--` parallel regions when concurrency exists.
4. **Stable state IDs:** Give every state a short, stable identifier (such as
   `WarmBuild`, `CIQueue`, `RenderFrame`) so requirements and docs can cite it
   cleanly.
5. **Color phases and hot spots:** Assign group color classes to phases and
   highlight risky, broken, or long-pole states distinctly (`bottleneck`,
   `breaks`, `risk`).

## Deterministic generation and validation script

Use the bundled deterministic helper script to validate structure (reachability,
non-terminal deadlocks, undefined states, arrow-count readability budget) and
emit consistent Mermaid `stateDiagram-v2` plus an optional Pele (`pele@1.9.0`)
SVG and self-contained light/dark HTML artifact:

```sh
# Build + validate canonical Mermaid (and optional SVG / HTML via pele@1.9.0) from a JSON spec
python3 PATH_TO_THIS_SKILL/scripts/state_diagram.py build spec.json \
  --out-mmd /tmp/diagram.mmd --out-html /tmp/diagram.html

# Validate a hand-authored Mermaid stateDiagram-v2 file
python3 PATH_TO_THIS_SKILL/scripts/state_diagram.py validate /tmp/diagram.mmd
```

JSON spec shape:

```json
{
  "title": "PR Delivery State Machine",
  "states": [
    {"id": "Draft", "label": "Draft Iteration", "group": "blue", "metrics": ["p50 18m"]},
    {"id": "CIRun", "label": "CI Checks", "group": "orange", "metrics": ["p50 5m 30s", "p90 6m 48s"], "highlight": "bottleneck"},
    {"id": "Merged", "label": "Merged on main", "group": "teal", "final": true}
  ],
  "transitions": [
    {"from": "[*]", "to": "Draft", "event": "open_pr"},
    {"from": "Draft", "to": "CIRun", "event": "mark_ready", "guard": "local checks pass", "metric": "queue p50 2m 55s"},
    {"from": "CIRun", "to": "Draft", "event": "check_failed", "action": "fix & push"},
    {"from": "CIRun", "to": "Merged", "event": "all_checks_green", "action": "squash_merge", "metric": "p50 1m"},
    {"from": "Merged", "to": "[*]"}
  ]
}
```

## Show both text and visual

1. Always validate before showing — fix any syntax, unreachable-state, or
   accidental deadlock error reported by `state_diagram.py`.
2. Keep the compact `stateDiagram-v2` block inline in text so agents and diffs
   read it deterministically.
3. Render the visual diagram for the reader:
   - Use `pele@1.9.0` (with `{ limit: 1_000_000, outputLimit: 8_000_000, maxEdges: 10_000 }`, themed via `--pele-*` CSS variables with light/dark support) via `state_diagram.py --out-html` / `--out-svg`.
   - Display the generated HTML inline if the host supports HTML previews, or
     save the SVG/HTML file in a scratch/output folder.
4. **No drifting diagram files:** Do not commit parallel hand-edited diagram
   docs that drift behind code; regenerate diagrams fresh from code and
   `git diff` whenever inspecting implemented behavior.
