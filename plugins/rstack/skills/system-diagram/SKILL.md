---
name: system-diagram
description: "Generate and validate system diagrams in two modes: architecture (components, boundaries, protocols, and edge metrics as Mermaid flowchart) and flow (lifecycles, request paths, workflows, and dev cycles as Mermaid stateDiagram-v2). A plan gets one top-level architecture diagram first, then flow diagrams only for critical paths."
---

# System diagram

Represent a system, feature, or workflow **both in text and visually** using
validated Mermaid rendered through `pele@1.9.0`.

## Choose the right mode

Pick the mode from what the reader needs (if unclear, ask):

- **`architecture` (Mermaid `flowchart` with `subgraph` boundaries):** Use for
  "architecture", "components", "how it fits together", or any new system.
  Shows the pieces and how they connect — clients, services, data stores,
  external services, and human gates — grouped into trust/deployment
  boundaries (browser, server, volume, third parties) with protocols and
  metrics on the edges.
- **`flow` (Mermaid `stateDiagram-v2`):** Use for lifecycles, request paths,
  write/retry state machines, workflows, and dev cycles.

**Plan rule:** A plan always starts with **one top-level `architecture`
diagram**, followed by **`flow` diagrams only for the critical paths** (for
example a document write lifecycle or an agent tool-call path). Architecture
component IDs serve as the canonical component section IDs across the plan.

## Source of truth & metrics

- **Plan:** Model every component, boundary, protocol, lifecycle stage, failure
  mode, recovery path, and concurrency lane implied by the plan.
- **Implemented feature or section of the codebase:** Derive components,
  boundaries, states, and transitions directly from actual code (services,
  handlers, enums, match arms, configs, tests, and `git log -p` / `git diff`).
  Never copy a stale Markdown doc or comment when code disagrees; flag
  discrepancies.
- **Workflow or dev cycle:** Derive stages, queues, reviews, retries, and
  completions from measured workflow data.

**Always reflect metrics in the diagram:** In **every** mode, annotate nodes
and edges directly with known or targeted performance, timing, latency,
throughput, frame-rate, memory, or queue metrics (for example
`GitStore [save p95 17ms MEASURED]` or `HTTPS / SSE (save-to-tab < 300ms p95)`).
Distinguish `MEASURED` values from `ASSUMED` targets.

## Authoring rules

1. **Reader's words:** Label components, states, and edges with what the reader
   sees or cares about, not raw internal variable names.
2. **Clarity budgets:** Aim for **25 edges or fewer** in `architecture` mode
   and **20 arrows or fewer** in `flow` mode. Group equivalent details under
   coarser labels before drawing noisy webs.
3. **Structural completeness:**
   - **`architecture`:** Every component must be connected by at least one edge;
     no edge may dangle; boundaries reflect real runtime or trust splits.
   - **`flow`:** Include explicit `[*]` start and terminal/rollback states,
     guards (`[guard]`), actions (`/ action`), failure/retry paths, and `--`
     parallel regions when concurrency exists; every state must be reachable
     from `[*]` and non-final states must have outgoing edges.
4. **Stable IDs:** Give every component and state a short, stable identifier
   (`storage`, `mcp`, `web`, `Committed`, `Locked`) so plans and registers can
   reference it cleanly.
5. **Color groups & hot spots:** Assign group color classes and highlight
   risky, broken, or long-pole nodes (`bottleneck`, `breaks`, `risk`).

## Deterministic generation and validation script

Use the bundled helper script to validate structure and emit canonical Mermaid
plus optional `pele@1.9.0` SVG and self-contained light/dark HTML:

```sh
# Build + validate architecture or flow diagram from JSON spec
python3 PATH_TO_THIS_SKILL/scripts/system_diagram.py build spec.json \
  --out-mmd /tmp/diagram.mmd --out-html /tmp/diagram.html

# Validate a hand-authored Mermaid flowchart or stateDiagram-v2 file
python3 PATH_TO_THIS_SKILL/scripts/system_diagram.py validate /tmp/diagram.mmd
```

### Architecture spec example

```json
{
  "mode": "architecture",
  "title": "System Architecture",
  "direction": "LR",
  "boundaries": [
    {"id": "browser", "label": "Browser"},
    {"id": "server", "label": "App Server"},
    {"id": "volume", "label": "Persistent Volume"},
    {"id": "third_party", "label": "Third Parties"}
  ],
  "components": [
    {"id": "web", "label": "Web Editor", "boundary": "browser", "shape": "client", "group": "blue", "metrics": ["bundle < 250KB"]},
    {"id": "mcp", "label": "HTTP + MCP Server", "boundary": "server", "shape": "service", "group": "purple"},
    {"id": "storage", "label": "Git + Checkout Store", "boundary": "volume", "shape": "store", "group": "teal", "metrics": ["save p95 17ms MEASURED"]},
    {"id": "auth", "label": "OAuth Provider", "boundary": "third_party", "shape": "external", "group": "orange"}
  ],
  "edges": [
    {"from": "web", "to": "mcp", "protocol": "HTTPS / SSE", "metric": "update < 300ms p95"},
    {"from": "mcp", "to": "storage", "protocol": "in-process", "label": "commit + checkout"},
    {"from": "mcp", "to": "auth", "protocol": "JWKS / OIDC", "label": "validate token"}
  ]
}
```

### Flow spec example

```json
{
  "mode": "flow",
  "title": "Document Write Lifecycle",
  "states": [
    {"id": "Received", "label": "Mutation Received", "group": "blue"},
    {"id": "Committed", "label": "Git Commit", "group": "purple", "metrics": ["p95 17ms MEASURED"]},
    {"id": "Visible", "label": "SSE Broadcast", "group": "teal", "metrics": ["< 300ms p95"], "final": true}
  ],
  "transitions": [
    {"from": "[*]", "to": "Received", "event": "save / batch"},
    {"from": "Received", "to": "Committed", "event": "apply", "guard": "base == HEAD"},
    {"from": "Committed", "to": "Visible", "event": "checkout + notify"},
    {"from": "Visible", "to": "[*]"}
  ]
}
```

## Show both text and visual

1. Always validate before showing — fix any dangling edge, disconnected
   component, unreachable state, or deadlock reported by `system_diagram.py`.
2. Keep the compact Mermaid block inline in text so agents and diffs read it
   deterministically.
3. Render visually via `pele@1.9.0` (`{ limit: 1_000_000, outputLimit: 8_000_000, maxEdges: 10_000 }`, themed with `--pele-*` light/dark CSS).
4. **Display rule (host-agnostic):** If the host can display HTML inline, show
   it; otherwise save the rendered HTML/SVG file and link it.
5. **No drifting diagram files:** Regenerate diagrams fresh from code and
   `git diff` when inspecting implemented systems rather than maintaining
   parallel hand-edited diagram docs.
