---
name: scope-work
description: "Size each implementation requirement directly with phase-by-phase justified time (edit, build_test, verify), explicit depends_on edges, and shared empirical rates from measure-dev-cycle. Never creates standalone scope or parallelism requirements."
---

# Scope work

Attach an empirically grounded, phase-by-phase `scope` object directly to every
**`implementation`** requirement (`kind: "implementation"`). **Assumptions**
(`kind: "assumption"`) inform design and are not work — never attach `scope` to
an assumption.

**No standalone scope or parallelism requirements:** Never create separate
requirements like "total work estimate" or "parallel lanes". Express
dependencies directly in `scope.depends_on`; totals, earliest start times
(`t+h:mm`), and the critical path are **derived deterministically** from the
register, never hand-authored as requirements.

## 1. Establish shared empirical `scope_model` via `measure-dev-cycle`

Use **`measure-dev-cycle`** to pull measured historical timings for the target
repository (`analyze --repo OWNER/REPO --since 60d`). If local history is empty
or stale, collect recent merged PRs first via `measure-dev-cycle`
(`collect --apply --repo OWNER/REPO --since 60d --limit 50`).

Record the shared model once at the top of the register under `scope_model`:

```json
"scope_model": {
  "failure_multiplier": 1.136,
  "reference": "owner/repo, 22 merged PRs: wall p50 15 min, failure rate 13.6%, retry 58 s",
  "confidence": "LOW_DATA_CONFIDENCE ±50%",
  "human_gates": [
    "External OAuth app registration",
    "Deployment credentials"
  ],
  "rates": [
    {
      "name": "Rust authoring",
      "value": "20 LOC/min",
      "evidence": "ASSUMED; calibrate on first three implementation requirements' actuals"
    },
    {
      "name": "Incremental compile-and-test cycle",
      "value": "3 min",
      "evidence": "ASSUMED incremental; cold build measured 58 s"
    }
  ]
}
```

- Every rate used in a phase `why` lives once in `scope_model.rates` with
  `name`, `value`, and `evidence` (`MEASURED` with command/receipt, or
  `ASSUMED` plus an explicit calibration plan).
- Keep human waits (`human_gates`) separate from automated/agent time.

## 2. Size every `implementation` requirement phase by phase

For each `implementation` requirement (splitting any piece above ~60–90 minutes
into smaller requirements rather than carrying a coarse lump), populate `scope`:

```json
"scope": {
  "first_pass_min": 30,
  "depends_on": ["R15"],
  "breakdown": {
    "edit":       {"min": 15, "why": "~240 LOC at 20 LOC/min = 12, plus 3 porting spike code."},
    "build_test": {"min": 10, "why": "~3 cycles at 3 min; crash-state fixtures are the slow ones."},
    "verify":     {"min": 5,  "why": "Rerun the 300-save benchmark, p95 against 100 ms."}
  },
  "basis": "What is built (~240 LOC, unit/fixture tests, prior spikes).",
  "risk":  "What could make it take longer, with the size of the blow-up if known."
}
```

Rules enforced by the register validator:

1. **Exact arithmetic:** `edit.min + build_test.min + verify.min` **must** equal
   `first_pass_min`. Do the real arithmetic from `scope_model.rates` — doing
   the math catches gut-feel inflation and exposes hidden complexity.
2. **Every phase needs a `why`:** Cite the rate and concrete work (`~LOC`, test
   cycles, benchmark/UI check) justifying each phase's minutes.
3. **Implementation-only `depends_on`:** Every ID in `depends_on` must be
   another `implementation` requirement (never an assumption), and the graph
   must be acyclic.
4. **Honest basis and risk:** State concretely what code/tests are produced
   (`basis`) and what failure mode could blow up the estimate (`risk`, with a
   magnitude when known).

## 3. Handle greenfield / thin-data areas honestly

When no close historical reference class exists (new language, new stack, new
hardware):

1. Set `scope_model.confidence` to `LOW_DATA_CONFIDENCE` with an explicit range
   (for example `±50%`) and anchor `reference` on the nearest available repo or
   verification tier.
2. Mark unmeasured rates in `scope_model.rates` as `ASSUMED` with concrete
   calibration targets (which early requirements will calibrate the rate).
3. Recommend a minimal time-boxed spike to measure real compile/test cycles
   before committing to a large schedule.
4. Once work lands, record actuals via `measure-dev-cycle` so future scoping
   for that stack becomes `MEASURED`.
