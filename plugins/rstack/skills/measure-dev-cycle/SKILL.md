---
name: measure-dev-cycle
description: Profile the complete end-to-end development cycle (edit, compile, test, PR, CI, review, merge) for a single task/PR or in aggregate across history, store structured timing records, and render a concise HTML Phase Duration Breakdown highlighting the long poles.
---

# Measure dev cycle

Measure the real end-to-end time it takes to take a change from first edit to
merged on `main`: **edit → compile → test/verify → PR open / draft → ready → CI
queue + jobs/steps → review/rework → merge**.

Break time down to seconds or minutes depending on scale, expose the **long
poles**, and store structured historical records for later analysis.

## Storage model (hybrid, zero repo clutter)

- **GitHub PR & Actions API** is the shared cross-machine source of truth for
  commits, draft/ready transitions, CI workflow/job/step timings, reviews, and
  merges across repositories.
- **Local append-only JSONL ledger** (`~/.local/state/dev-cycle/cycles.jsonl`,
  override with `--store` or `DEV_CYCLE_STORE`) caches collected PR/CI records
  and captures local pre-PR phases (`edit`, `compile`, `test`, `device_apply`,
  `verify`).
- **PR timing snippet (cross-machine pre-PR sharing):** Use `pr-snippet` to
  attach a compact `<!-- dev-cycle: {...} -->` JSON block to a PR body so local
  pre-PR timings travel with the PR across machines without committing
  telemetry files to repositories.

## CLI workflow (`scripts/dev_cycle.py`)

Run `python3 PATH_TO_THIS_SKILL/scripts/dev_cycle.py --help` for full options.
Mutating commands preview by default and require exact `--apply` to write files
or fetch/cache records.

### 1. Capture local pre-PR spans

Record phase spans as you work (or import a compatible JSONL work journal via
`--from-journal`):

```sh
python3 PATH_TO_THIS_SKILL/scripts/dev_cycle.py record --apply \
  --repo owner/repo --task pr-412 --phase compile \
  --started 2026-11-25T18:00:00Z --ended 2026-11-25T18:02:14Z \
  --status passed --subsystem core --warm warm --note "incremental build"

python3 PATH_TO_THIS_SKILL/scripts/dev_cycle.py pr-snippet --task pr-412
```

### 2. Collect single-PR or aggregate GitHub history

Pull exact PR commit, draft/ready, CI job/step, review, and merge timings (plus
any embedded `<!-- dev-cycle: ... -->` local spans) via `gh api`:

```sh
# Single PR
python3 PATH_TO_THIS_SKILL/scripts/dev_cycle.py collect --apply --repo owner/repo --pr 412

# Aggregate history (last 30 days)
python3 PATH_TO_THIS_SKILL/scripts/dev_cycle.py collect --apply --repo owner/repo --since 30d --limit 50
```

### 3. Analyze long poles and render the concise HTML breakdown

```sh
# Single-PR breakdown (JSON, read-only)
python3 PATH_TO_THIS_SKILL/scripts/dev_cycle.py analyze --repo owner/repo --pr 412

# Aggregate breakdown across recent PRs (p50/p75/p90, failure rate, ranked long poles)
python3 PATH_TO_THIS_SKILL/scripts/dev_cycle.py analyze --repo owner/repo --since 30d

# Concise HTML phase duration breakdown from the bundled template
python3 PATH_TO_THIS_SKILL/scripts/dev_cycle.py render --apply --repo owner/repo --pr 412 \
  --output /tmp/dev-cycle-pr412.html
python3 PATH_TO_THIS_SKILL/scripts/dev_cycle.py render --apply --repo owner/repo --since 30d \
  --output /tmp/dev-cycle-aggregate.html
```

Keep the HTML view strictly concise: one **Phase Duration Breakdown (Empirical
Scope Reference)** table sorted by time share with bolding and color
highlighting on the **long poles**, plus the one-line summary of wall clock or
first-pass vs failure-adjusted p50.

## Optional deep drill-down tools (reuse existing OSS)

When a long pole points inside CI jobs or a specific compiler:

- **GitHub Actions step/flaky/regression drill-down:** `ci-time-tracker` or
  `ote` (`stefanpenner/otel-explorer`, exports Perfetto `.pftrace`).
- **Rust builds:** `cargo build --timings` (built-in HTML timing graph).
- **Ninja / C++ builds:** `.ninja_log` analysis / `ninjatracing`.
