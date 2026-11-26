#!/usr/bin/env python3
"""Standalone dev-cycle profiler, analyzer, and HTML breakdown renderer.

Hybrid storage (zero repository clutter):
- GitHub PR & Actions API (via `gh api`) provides commits, draft/ready, CI runs/jobs/steps,
  reviews, and merges across machines.
- Local append-only JSONL ledger (`~/.local/state/dev-cycle/cycles.jsonl` by default, or
  `--store` / `DEV_CYCLE_STORE`) caches collected PR cycles and stores local pre-PR spans
  (edit, compile, test, device_apply, verify), including imports from JSONL work journals.
- `pr-snippet` emits a compact `<!-- dev-cycle: {...} -->` HTML comment so local pre-PR
  spans travel on PR descriptions and merge seamlessly during `collect`.

Python 3.9+ compatible, standard library only. Every mutating or network/cache-writing verb
previews without side effects until exact `--apply`.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import datetime as dt
import fcntl
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

SCHEMA_VERSION = 1
DEFAULT_STORE_REL = Path('.local/state/dev-cycle/cycles.jsonl')
DEFAULT_TEMPLATE = Path(__file__).resolve().parent.parent / 'assets' / 'phase_breakdown.html'
SNIPPET_RE = re.compile(r'<!--\s*(?:[a-z0-9_-]+-)?dev-cycle:\s*(\{.*?\})\s*-->', re.S)

PHASES = (
    'edit', 'compile', 'test', 'device_apply', 'verify',
    'pr_prep', 'draft', 'ci_queue', 'ci_run', 'review', 'rework', 'merge', 'wait',
)
KINDS = ('active', 'queue', 'human_wait', 'retry')
STATUSES = ('passed', 'failed', 'cancelled', 'skipped', 'unknown')
WARM_VALUES = ('warm', 'cold', 'unknown')
SOURCES = ('local', 'journal', 'github', 'pr_snippet')

PHASE_DEFAULT_KIND = {
    'edit': 'active',
    'compile': 'active',
    'test': 'active',
    'device_apply': 'active',
    'verify': 'active',
    'pr_prep': 'active',
    'draft': 'active',
    'ci_queue': 'queue',
    'ci_run': 'active',
    'review': 'human_wait',
    'rework': 'retry',
    'merge': 'active',
    'wait': 'human_wait',
}

JOURNAL_CATEGORY_PHASE = {
    'compiling': 'compile',
    'tests': 'test',
    'diagnostics': 'verify',
    'research': 'edit',
    'build-failure': 'rework',
    'recovery': 'rework',
    'implementation': 'edit',
    'tooling': 'edit',
    'cleanup': 'verify',
    'coordination': 'review',
    'coverage': 'verify',
    'evidence': 'verify',
    'blocked': 'wait',
}


class CycleError(ValueError):
    """Invalid input, schema error, or external collection failure."""


def default_store(env_var='DEV_CYCLE_STORE', default_rel=DEFAULT_STORE_REL):
    override = os.environ.get(env_var)
    if override:
        return Path(override).expanduser()
    return Path.home() / default_rel


def parse_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        raise CycleError('timestamp must be a nonempty ISO-8601 string')
    text = value.strip()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError as error:
        raise CycleError('invalid ISO-8601 timestamp: ' + value) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CycleError('timestamp must include timezone: ' + value)
    return parsed.astimezone(dt.timezone.utc)


def iso_utc(value):
    if isinstance(value, str):
        value = parse_timestamp(value)
    return value.astimezone(dt.timezone.utc).isoformat().replace('+00:00', 'Z')


def now_utc():
    return iso_utc(dt.datetime.now(dt.timezone.utc))


def parse_since(value, *, reference=None):
    if not value:
        return None
    now = reference or dt.datetime.now(dt.timezone.utc)
    match = re.fullmatch(r'(\d+)([hdwm])', value.strip().lower())
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        if unit == 'h':
            return now - dt.timedelta(hours=amount)
        if unit == 'd':
            return now - dt.timedelta(days=amount)
        if unit == 'w':
            return now - dt.timedelta(weeks=amount)
        if unit == 'm':
            return now - dt.timedelta(days=amount * 30)
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value.strip()):
        return parse_timestamp(value.strip() + 'T00:00:00Z')
    return parse_timestamp(value)


def normalize_span(raw):
    if not isinstance(raw, dict):
        raise CycleError('span must be a JSON object')
    phase = raw.get('phase')
    if phase not in PHASES:
        raise CycleError('unsupported phase: ' + str(phase))
    started = parse_timestamp(raw.get('started_at'))
    ended = parse_timestamp(raw.get('ended_at'))
    if ended < started:
        raise CycleError('span ended_at precedes started_at')
    duration = round((ended - started).total_seconds(), 3)
    kind = raw.get('kind') or PHASE_DEFAULT_KIND[phase]
    if kind not in KINDS:
        raise CycleError('unsupported span kind: ' + str(kind))
    status = raw.get('status') or 'passed'
    if status not in STATUSES:
        raise CycleError('unsupported span status: ' + str(status))
    source = raw.get('source') or 'local'
    if source not in SOURCES:
        raise CycleError('unsupported span source: ' + str(source))
    warm = raw.get('warm')
    if warm is not None and warm not in WARM_VALUES:
        raise CycleError('unsupported warm state: ' + str(warm))
    span = {
        'phase': phase,
        'label': str(raw.get('label') or phase).strip() or phase,
        'started_at': iso_utc(started),
        'ended_at': iso_utc(ended),
        'duration_seconds': duration,
        'kind': kind,
        'status': status,
        'source': source,
    }
    for optional in ('repo', 'task', 'subsystem', 'warm', 'source_commit', 'note'):
        if raw.get(optional) not in (None, ''):
            span[optional] = str(raw[optional])
    if raw.get('pr') is not None:
        if type(raw['pr']) is not int or raw['pr'] < 1:
            raise CycleError('pr must be a positive integer')
        span['pr'] = raw['pr']
    return span


def append_records(store_path, records):
    store_path = Path(store_path)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = store_path.parent / (store_path.name + '.lock')
    lines = [json.dumps(rec, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n'
             for rec in records]
    with ExitStack() as stack:
        lock_file = stack.enter_context(lock_path.open('a+'))
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        output = stack.enter_context(store_path.open('a', encoding='utf-8'))
        for line in lines:
            output.write(line)
        output.flush()
        os.fsync(output.fileno())


def read_records(path):
    path = Path(path)
    if not path.is_file():
        return []
    text = path.read_text(encoding='utf-8').strip()
    if not text:
        return []
    if text.startswith('[') or text.startswith('{'):
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, list):
            return loaded
        if isinstance(loaded, dict) and 'records' in loaded and isinstance(loaded['records'], list):
            return loaded['records']
        if isinstance(loaded, dict) and loaded.get('record_type') in ('span', 'pr_cycle'):
            return [loaded]
    records = []
    for index, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise CycleError(f'{path}:{index}: invalid JSONL record: {error}') from error
    return records


def atomic_write_text(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix='.cycle-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def spans_from_journal(journal_dir, *, repo, task, pr=None, subsystem=None):
    journal_path = Path(journal_dir)
    if journal_path.is_dir():
        journal_path = journal_path / 'events.jsonl'
    if not journal_path.is_file():
        raise CycleError('work journal events.jsonl not found: ' + str(journal_path))
    events = read_records(journal_path)
    if not events:
        return []

    spans = []
    open_blockers = {}
    timed_events = []
    for ev in events:
        when = ev.get('occurred_at') or ev.get('recorded_at')
        if not when:
            continue
        try:
            ts = parse_timestamp(when)
        except CycleError:
            continue
        blocker = ev.get('blocker')
        if isinstance(blocker, dict) and blocker.get('id') and blocker.get('at'):
            bid = str(blocker['id'])
            if blocker.get('edge') == 'start':
                open_blockers[bid] = (parse_timestamp(blocker['at']), blocker.get('reason') or 'blocked')
            elif blocker.get('edge') == 'end' and bid in open_blockers:
                bstart, breason = open_blockers.pop(bid)
                bend = parse_timestamp(blocker['at'])
                if bend >= bstart:
                    spans.append(normalize_span({
                        'repo': repo,
                        'task': task,
                        'pr': pr,
                        'phase': 'wait',
                        'label': 'blocker: ' + str(breason)[:60],
                        'started_at': iso_utc(bstart),
                        'ended_at': iso_utc(bend),
                        'kind': 'human_wait',
                        'status': 'passed',
                        'subsystem': subsystem,
                        'source': 'journal',
                    }))
        timed_events.append((ts, ev))

    timed_events.sort(key=lambda item: item[0])
    for index, (ts, ev) in enumerate(timed_events):
        next_ts = timed_events[index + 1][0] if index + 1 < len(timed_events) else ts
        if next_ts < ts:
            continue
        category = str(ev.get('category') or 'implementation')
        phase = JOURNAL_CATEGORY_PHASE.get(category, 'edit')
        raw_status = str(ev.get('status') or '').lower()
        status = 'failed' if any(tok in raw_status for tok in ('fail', 'error')) else 'passed'
        label = str(ev.get('headline') or ev.get('operation') or ev.get('summary') or phase)[:72]
        spans.append(normalize_span({
            'repo': repo,
            'task': task,
            'pr': pr,
            'phase': phase,
            'label': label,
            'started_at': iso_utc(ts),
            'ended_at': iso_utc(next_ts),
            'status': status,
            'subsystem': subsystem,
            'source': 'journal',
            'note': str(ev.get('summary') or '')[:200],
        }))
    return spans


def parse_pr_snippet(body, *, repo, pr):
    if not body:
        return []
    spans = []
    for match in SNIPPET_RE.finditer(body):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get('spans'), list):
            continue
        task = str(payload.get('task') or f'pr-{pr}')
        for raw in payload['spans']:
            if not isinstance(raw, dict):
                continue
            merged = dict(raw)
            merged.setdefault('repo', repo)
            merged.setdefault('task', task)
            merged.setdefault('pr', pr)
            merged['source'] = 'pr_snippet'
            try:
                spans.append(normalize_span(merged))
            except CycleError:
                continue
    return spans


def format_pr_snippet(repo, task, spans, *, tag='dev-cycle'):
    compact = []
    for s in spans:
        entry = {
            'phase': s['phase'],
            'label': s['label'],
            'started_at': s['started_at'],
            'ended_at': s['ended_at'],
            'kind': s['kind'],
            'status': s['status'],
        }
        for opt in ('subsystem', 'warm'):
            if s.get(opt):
                entry[opt] = s[opt]
        compact.append(entry)
    payload = {'schema': SCHEMA_VERSION, 'repo': repo, 'task': task, 'spans': compact}
    return f'<!-- {tag}: ' + json.dumps(payload, sort_keys=True, separators=(',', ':')) + ' -->'


def gh_api_json(gh_bin, endpoint, *, params=None):
    cmd = [gh_bin, 'api', endpoint]
    if params:
        for key, value in params.items():
            cmd.extend(['-f', f'{key}={value}'])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise CycleError(f'gh api {endpoint} failed (exit {result.returncode}): {result.stderr.strip()}')
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise CycleError(f'gh api {endpoint} returned invalid JSON') from error


def infer_subsystem(file_paths):
    if not file_paths:
        return None
    counts = {}
    for path in file_paths:
        parts = [p for p in str(path).split('/') if p]
        if not parts:
            continue
        bucket = parts[0] if len(parts) > 1 else 'root'
        counts[bucket] = counts.get(bucket, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _gh_conclusion_status(conclusion):
    value = str(conclusion or '').lower()
    if value == 'success':
        return 'passed'
    if value == 'cancelled':
        return 'cancelled'
    if value in ('skipped', 'neutral'):
        return 'skipped'
    if value in ('failure', 'timed_out', 'action_required', 'startup_failure'):
        return 'failed'
    return 'unknown'


def collect_pr_cycle(gh_bin, repo, pr_number):
    pr = gh_api_json(gh_bin, f'repos/{repo}/pulls/{pr_number}')
    commits = gh_api_json(gh_bin, f'repos/{repo}/pulls/{pr_number}/commits')
    reviews = gh_api_json(gh_bin, f'repos/{repo}/pulls/{pr_number}/reviews')
    files_data = gh_api_json(gh_bin, f'repos/{repo}/pulls/{pr_number}/files')
    timeline = gh_api_json(gh_bin, f'repos/{repo}/issues/{pr_number}/timeline')

    created_at = pr.get('created_at')
    merged_at = pr.get('merged_at')
    closed_at = pr.get('closed_at')
    end_at = merged_at or closed_at or pr.get('updated_at') or created_at
    task = f'pr-{pr_number}'
    subsystem = infer_subsystem([f.get('filename', '') for f in files_data if isinstance(f, dict)])

    commit_times = []
    commit_shas = []
    for item in commits if isinstance(commits, list) else []:
        if not isinstance(item, dict):
            continue
        sha = item.get('sha')
        if sha:
            commit_shas.append(sha)
        info = item.get('commit') or {}
        when = (info.get('committer') or {}).get('date') or (info.get('author') or {}).get('date')
        if when:
            try:
                commit_times.append(parse_timestamp(when))
            except CycleError:
                pass
    first_commit_dt = min(commit_times) if commit_times else None

    ready_at = created_at
    for ev in timeline if isinstance(timeline, list) else []:
        if isinstance(ev, dict) and ev.get('event') == 'ready_for_review' and ev.get('created_at'):
            ready_at = ev['created_at']

    spans = parse_pr_snippet(pr.get('body') or '', repo=repo, pr=pr_number)

    if first_commit_dt and created_at:
        created_dt = parse_timestamp(created_at)
        if first_commit_dt <= created_dt:
            spans.append(normalize_span({
                'repo': repo, 'task': task, 'pr': pr_number,
                'phase': 'edit', 'label': 'commits before PR open',
                'started_at': iso_utc(first_commit_dt), 'ended_at': iso_utc(created_dt),
                'kind': 'active', 'status': 'passed', 'subsystem': subsystem, 'source': 'github',
            }))

    if created_at and ready_at:
        c_dt, r_dt = parse_timestamp(created_at), parse_timestamp(ready_at)
        if r_dt > c_dt:
            spans.append(normalize_span({
                'repo': repo, 'task': task, 'pr': pr_number,
                'phase': 'draft', 'label': 'draft iteration',
                'started_at': iso_utc(c_dt), 'ended_at': iso_utc(r_dt),
                'kind': 'active', 'status': 'passed', 'subsystem': subsystem, 'source': 'github',
            }))

    head_sha = (pr.get('head') or {}).get('sha')
    queried_shas = list(dict.fromkeys(([head_sha] if head_sha else []) + commit_shas[-5:]))
    ci_runs = []
    seen_run_ids = set()
    for sha in queried_shas:
        data = gh_api_json(gh_bin, f'repos/{repo}/actions/runs?head_sha={sha}&per_page=50')
        for run in data.get('workflow_runs', []) if isinstance(data, dict) else []:
            rid = run.get('id')
            if rid is None or rid in seen_run_ids:
                continue
            seen_run_ids.add(rid)
            ci_runs.append(run)

    ci_failed = 0
    for run in ci_runs:
        run_status = _gh_conclusion_status(run.get('conclusion'))
        if run_status == 'skipped':
            continue
        if run_status == 'failed':
            ci_failed += 1
        jobs_payload = gh_api_json(gh_bin, f'repos/{repo}/actions/runs/{run["id"]}/jobs?per_page=100')
        jobs = jobs_payload.get('jobs', []) if isinstance(jobs_payload, dict) else []
        wf_name = str(run.get('name') or 'ci')
        if not jobs and run.get('created_at') and run.get('updated_at'):
            r_start = parse_timestamp(run['created_at'])
            r_end = parse_timestamp(run['updated_at'])
            if r_end >= r_start:
                spans.append(normalize_span({
                    'repo': repo, 'task': task, 'pr': pr_number,
                    'phase': 'ci_run', 'label': wf_name,
                    'started_at': iso_utc(r_start), 'ended_at': iso_utc(r_end),
                    'kind': 'retry' if run_status == 'failed' else 'active',
                    'status': run_status, 'subsystem': subsystem, 'source': 'github',
                }))
            continue
        for job in jobs:
            if not isinstance(job, dict):
                continue
            jname = f'{wf_name} / {job.get("name") or "job"}'
            j_status = _gh_conclusion_status(job.get('conclusion'))
            if j_status == 'skipped':
                continue
            j_created = job.get('created_at') or run.get('created_at')
            j_started = job.get('started_at')
            j_completed = job.get('completed_at')
            if j_created and j_started:
                q_s, q_e = parse_timestamp(j_created), parse_timestamp(j_started)
                if q_e > q_s:
                    spans.append(normalize_span({
                        'repo': repo, 'task': task, 'pr': pr_number,
                        'phase': 'ci_queue', 'label': f'queue: {jname}',
                        'started_at': iso_utc(q_s), 'ended_at': iso_utc(q_e),
                        'kind': 'queue', 'status': 'passed', 'subsystem': subsystem, 'source': 'github',
                    }))
            steps = job.get('steps') or []
            added_step = False
            for step in steps:
                if not isinstance(step, dict) or not step.get('started_at') or not step.get('completed_at'):
                    continue
                s_s, s_e = parse_timestamp(step['started_at']), parse_timestamp(step['completed_at'])
                if s_e < s_s:
                    continue
                s_status = _gh_conclusion_status(step.get('conclusion'))
                if s_status == 'skipped':
                    continue
                spans.append(normalize_span({
                    'repo': repo, 'task': task, 'pr': pr_number,
                    'phase': 'ci_run', 'label': f'{jname} / {step.get("name") or "step"}',
                    'started_at': iso_utc(s_s), 'ended_at': iso_utc(s_e),
                    'kind': 'retry' if (j_status == 'failed' or s_status == 'failed') else 'active',
                    'status': s_status, 'subsystem': subsystem, 'source': 'github',
                }))
                added_step = True
            if not added_step and j_started and j_completed:
                x_s, x_e = parse_timestamp(j_started), parse_timestamp(j_completed)
                if x_e >= x_s:
                    spans.append(normalize_span({
                        'repo': repo, 'task': task, 'pr': pr_number,
                        'phase': 'ci_run', 'label': jname,
                        'started_at': iso_utc(x_s), 'ended_at': iso_utc(x_e),
                        'kind': 'retry' if j_status == 'failed' else 'active',
                        'status': j_status, 'subsystem': subsystem, 'source': 'github',
                    }))

    review_times = []
    approval_times = []
    for rev in reviews if isinstance(reviews, list) else []:
        if not isinstance(rev, dict) or not rev.get('submitted_at'):
            continue
        r_dt = parse_timestamp(rev['submitted_at'])
        review_times.append(r_dt)
        if str(rev.get('state') or '').upper() == 'APPROVED':
            approval_times.append(r_dt)

    if ready_at and review_times:
        ready_dt = parse_timestamp(ready_at)
        last_rev = max(review_times)
        if last_rev > ready_dt:
            spans.append(normalize_span({
                'repo': repo, 'task': task, 'pr': pr_number,
                'phase': 'review', 'label': 'review pickup & rounds',
                'started_at': iso_utc(ready_dt), 'ended_at': iso_utc(last_rev),
                'kind': 'human_wait', 'status': 'passed', 'subsystem': subsystem, 'source': 'github',
            }))

    if merged_at:
        merge_dt = parse_timestamp(merged_at)
        merge_start = max(approval_times) if approval_times else (parse_timestamp(ready_at) if ready_at else None)
        if merge_start and merge_dt >= merge_start:
            spans.append(normalize_span({
                'repo': repo, 'task': task, 'pr': pr_number,
                'phase': 'merge', 'label': 'approval/ready to merge',
                'started_at': iso_utc(merge_start), 'ended_at': iso_utc(merge_dt),
                'kind': 'active', 'status': 'passed', 'subsystem': subsystem, 'source': 'github',
            }))

    state = 'MERGED' if merged_at else str(pr.get('state') or 'OPEN').upper()
    return {
        'schema': SCHEMA_VERSION,
        'record_type': 'pr_cycle',
        'repo': repo,
        'pr': pr_number,
        'title': str(pr.get('title') or ''),
        'url': str(pr.get('html_url') or f'https://github.com/{repo}/pull/{pr_number}'),
        'state': state,
        'created_at': iso_utc(created_at) if created_at else None,
        'ready_at': iso_utc(ready_at) if ready_at else None,
        'merged_at': iso_utc(merged_at) if merged_at else None,
        'end_at': iso_utc(end_at) if end_at else None,
        'first_commit_at': iso_utc(first_commit_dt) if first_commit_dt else None,
        'additions': int(pr.get('additions') or 0),
        'deletions': int(pr.get('deletions') or 0),
        'changed_files': int(pr.get('changed_files') or len(files_data or [])),
        'commits_count': len(commits) if isinstance(commits, list) else 0,
        'subsystem': subsystem,
        'ci_runs_count': len(ci_runs),
        'ci_failed_runs': ci_failed,
        'spans': spans,
        'collected_at': now_utc(),
    }


def percentile(values, p):
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    rank = (len(ordered) - 1) * p
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return round(ordered[low], 3)
    weight = rank - low
    return round(ordered[low] * (1.0 - weight) + ordered[high] * weight, 3)


def wall_clock_seconds(spans):
    if not spans:
        return 0.0
    starts = [parse_timestamp(s['started_at']) for s in spans]
    ends = [parse_timestamp(s['ended_at']) for s in spans]
    return round(max(0.0, (max(ends) - min(starts)).total_seconds()), 3)


def union_seconds(spans):
    if not spans:
        return 0.0
    intervals = sorted((parse_timestamp(s['started_at']), parse_timestamp(s['ended_at'])) for s in spans)
    total = 0.0
    cur_s, cur_e = intervals[0]
    for s, e in intervals[1:]:
        if s <= cur_e:
            if e > cur_e:
                cur_e = e
        else:
            total += (cur_e - cur_s).total_seconds()
            cur_s, cur_e = s, e
    total += (cur_e - cur_s).total_seconds()
    return round(total, 3)


def compute_long_poles(spans, denominator):
    grouped = {}
    for s in spans:
        key = (s['phase'], s['label'], s['kind'])
        entry = grouped.setdefault(key, {'phase': s['phase'], 'label': s['label'], 'kind': s['kind'],
                                         'duration_seconds': 0.0, 'count': 0, 'failed_count': 0})
        entry['duration_seconds'] += float(s['duration_seconds'])
        entry['count'] += 1
        if s.get('status') == 'failed':
            entry['failed_count'] += 1
    denom = denominator if denominator > 0 else 1.0
    poles = []
    for entry in grouped.values():
        dur = round(entry['duration_seconds'], 3)
        poles.append({
            **entry,
            'duration_seconds': dur,
            'share': round(dur / denom, 4),
        })
    poles.sort(key=lambda item: (-item['duration_seconds'], item['phase'], item['label']))
    return poles


def analyze_records(records, *, repo=None, pr=None, task=None, since=None, subsystem=None, title=None):
    since_dt = parse_since(since) if since else None

    pr_cycles = {}
    loose_spans = []
    for rec in records:
        rtype = rec.get('record_type')
        if rtype == 'pr_cycle':
            key = (rec.get('repo'), rec.get('pr'))
            prev = pr_cycles.get(key)
            if prev is None or str(rec.get('collected_at') or '') >= str(prev.get('collected_at') or ''):
                pr_cycles[key] = rec
        elif rtype == 'span':
            loose_spans.append(rec)

    def matches_filters(r_repo, r_pr, r_task, r_sub, ref_time):
        if repo and r_repo != repo:
            return False
        if pr is not None and r_pr != pr:
            return False
        if task and r_task != task:
            return False
        if subsystem and r_sub != subsystem:
            return False
        if since_dt and ref_time:
            try:
                if parse_timestamp(ref_time) < since_dt:
                    return False
            except CycleError:
                pass
        return True

    items = []
    consumed_span_ids = set()
    for (_, pr_num), cycle in sorted(pr_cycles.items(), key=lambda kv: str(kv[1].get('created_at') or '')):
        c_repo = cycle.get('repo')
        c_task = f'pr-{pr_num}'
        ref_time = cycle.get('merged_at') or cycle.get('created_at') or cycle.get('collected_at')
        if not matches_filters(c_repo, pr_num, c_task, cycle.get('subsystem'), ref_time):
            continue
        spans = [normalize_span(s) for s in cycle.get('spans', [])]
        for idx, ls in enumerate(loose_spans):
            if ls.get('repo') == c_repo and (ls.get('pr') == pr_num or ls.get('task') == c_task):
                spans.append(normalize_span(ls))
                consumed_span_ids.add(idx)
        items.append({
            'id': f'{c_repo}#{pr_num}',
            'repo': c_repo,
            'pr': pr_num,
            'task': c_task,
            'title': cycle.get('title') or '',
            'state': cycle.get('state') or 'UNKNOWN',
            'subsystem': cycle.get('subsystem'),
            'ci_runs_count': int(cycle.get('ci_runs_count') or 0),
            'ci_failed_runs': int(cycle.get('ci_failed_runs') or 0),
            'spans': spans,
        })

    grouped_tasks = {}
    for idx, ls in enumerate(loose_spans):
        if idx in consumed_span_ids:
            continue
        s = normalize_span(ls)
        s_repo = s.get('repo') or 'local'
        s_task = s.get('task') or (f'pr-{s["pr"]}' if s.get('pr') else 'default')
        if not matches_filters(s_repo, s.get('pr'), s_task, s.get('subsystem'), s['started_at']):
            continue
        grouped_tasks.setdefault((s_repo, s_task), []).append(s)

    for (s_repo, s_task), spans in sorted(grouped_tasks.items()):
        items.append({
            'id': f'{s_repo}:{s_task}',
            'repo': s_repo,
            'pr': spans[0].get('pr'),
            'task': s_task,
            'title': s_task,
            'state': 'LOCAL',
            'subsystem': spans[0].get('subsystem'),
            'ci_runs_count': sum(1 for s in spans if s['phase'] == 'ci_run'),
            'ci_failed_runs': sum(1 for s in spans if s['phase'] == 'ci_run' and s['status'] == 'failed'),
            'spans': spans,
        })

    single_mode = pr is not None or task is not None
    all_spans = [s for item in items for s in item['spans']]
    by_kind = {k: 0.0 for k in KINDS}
    for s in all_spans:
        by_kind[s['kind']] += float(s['duration_seconds'])
    by_kind = {k: round(v, 3) for k, v in by_kind.items()}
    total_span_seconds = round(sum(by_kind.values()), 3)
    failed_spans = sum(1 for s in all_spans if s['status'] == 'failed')
    long_poles = compute_long_poles(all_spans, total_span_seconds)

    filters = {k: v for k, v in {'repo': repo, 'pr': pr, 'task': task, 'since': since,
                                 'subsystem': subsystem}.items() if v is not None}

    by_phase_vals = {}
    phase_kind = {}
    for s in all_spans:
        by_phase_vals.setdefault(s['phase'], []).append(float(s['duration_seconds']))
        phase_kind.setdefault(s['phase'], s['kind'])
    denom = total_span_seconds if total_span_seconds > 0 else 1.0
    phase_stats = []
    for phase, vals in by_phase_vals.items():
        psum = round(sum(vals), 3)
        phase_stats.append({
            'phase': phase,
            'kind': phase_kind[phase],
            'count': len(vals),
            'total_seconds': psum,
            'share': round(psum / denom, 4),
            'min_seconds': round(min(vals), 3),
            'p50_seconds': percentile(vals, 0.50),
            'p75_seconds': percentile(vals, 0.75),
            'p90_seconds': percentile(vals, 0.90),
            'mean_seconds': round(psum / len(vals), 3),
            'max_seconds': round(max(vals), 3),
        })
    phase_stats.sort(key=lambda row: (-row['total_seconds'], row['phase']))
    for idx, row in enumerate(phase_stats):
        row['long_pole'] = (idx == 0) or (idx < 3 and row['share'] >= 0.10)

    if single_mode:
        wall = wall_clock_seconds(all_spans)
        unioned = union_seconds(all_spans)
        parallelism = round(total_span_seconds / wall, 2) if wall > 0 else 1.0
        phase_totals = {}
        for s in all_spans:
            phase_totals[s['phase']] = round(phase_totals.get(s['phase'], 0.0) + s['duration_seconds'], 3)
        default_title = items[0]['id'] + (' — ' + items[0]['title'] if items and items[0]['title'] else '') if items else (task or f'PR #{pr}')
        return {
            'schema': SCHEMA_VERSION,
            'mode': 'single',
            'title': title or default_title,
            'generated_at': now_utc(),
            'filters': filters,
            'summary': {
                'items_count': len(items),
                'span_count': len(all_spans),
                'failed_spans': failed_spans,
                'wall_clock_seconds': wall,
                'unioned_busy_seconds': unioned,
                'summed_span_seconds': total_span_seconds,
                'parallelism_ratio': parallelism,
                'by_kind': by_kind,
                'by_phase': phase_totals,
            },
            'long_poles': long_poles[:15],
            'phase_stats': phase_stats,
            'spans': sorted(all_spans, key=lambda s: (s['started_at'], s['ended_at'], s['phase'])),
        }

    item_summaries = []
    wall_values = []
    first_pass_walls = []
    failed_items = 0
    retry_overhead_values = []
    for item in items:
        ispans = item['spans']
        iwall = wall_clock_seconds(ispans)
        ifailed = sum(1 for s in ispans if s['status'] == 'failed')
        iretry = round(sum(s['duration_seconds'] for s in ispans if s['kind'] == 'retry' or s['status'] == 'failed'), 3)
        ipoles = compute_long_poles(ispans, sum(s['duration_seconds'] for s in ispans))
        top_pole = f"{ipoles[0]['label']} ({round(ipoles[0]['duration_seconds'], 1)}s)" if ipoles else None
        wall_values.append(iwall)
        if ifailed > 0 or item['ci_failed_runs'] > 0:
            failed_items += 1
            retry_overhead_values.append(iretry)
        else:
            first_pass_walls.append(iwall)
        item_summaries.append({
            'id': item['id'],
            'repo': item['repo'],
            'pr': item['pr'],
            'title': item['title'],
            'state': item['state'],
            'subsystem': item['subsystem'],
            'wall_clock_seconds': iwall,
            'span_count': len(ispans),
            'failed_spans': ifailed,
            'retry_seconds': iretry,
            'top_long_pole': top_pole,
        })

    failure_rate = round(failed_items / len(items), 4) if items else 0.0
    p50_wall = percentile(wall_values, 0.50)
    p90_wall = percentile(wall_values, 0.90)
    first_pass_p50 = percentile(first_pass_walls, 0.50) if first_pass_walls else p50_wall
    avg_retry = round(sum(retry_overhead_values) / len(retry_overhead_values), 3) if retry_overhead_values else 0.0
    failure_adjusted_p50 = round(first_pass_p50 + failure_rate * avg_retry, 3)

    return {
        'schema': SCHEMA_VERSION,
        'mode': 'aggregate',
        'title': title or (f'Dev Cycle Aggregate — {repo}' if repo else 'Dev Cycle Aggregate'),
        'generated_at': now_utc(),
        'filters': filters,
        'summary': {
            'items_count': len(items),
            'span_count': len(all_spans),
            'failed_spans': failed_spans,
            'failed_items': failed_items,
            'failure_rate': failure_rate,
            'wall_clock_p50_seconds': p50_wall,
            'wall_clock_p75_seconds': percentile(wall_values, 0.75),
            'wall_clock_p90_seconds': p90_wall,
            'summed_span_seconds': total_span_seconds,
            'by_kind': by_kind,
            'queue_share': round(by_kind['queue'] / denom, 4) if total_span_seconds > 0 else 0.0,
            'human_wait_share': round(by_kind['human_wait'] / denom, 4) if total_span_seconds > 0 else 0.0,
            'retry_share': round(by_kind['retry'] / denom, 4) if total_span_seconds > 0 else 0.0,
        },
        'scope_reference': {
            'sample_size': len(items),
            'sample_ids': [it['id'] for it in item_summaries[:20]],
            'first_pass_p50_seconds': first_pass_p50,
            'failure_rate': failure_rate,
            'average_retry_penalty_seconds': avg_retry,
            'failure_adjusted_p50_seconds': failure_adjusted_p50,
            'formula': 'first_pass_p50_seconds + failure_rate * average_retry_penalty_seconds',
        },
        'long_poles': long_poles[:15],
        'phase_stats': phase_stats,
        'items': item_summaries,
    }


def render_html(report, *, template_text=None, template_path=None):
    if template_text is None:
        source = Path(template_path) if template_path else DEFAULT_TEMPLATE
        if not source.is_file():
            raise CycleError('HTML template not found: ' + str(source))
        template_text = source.read_text(encoding='utf-8')
    safe_json = json.dumps(report, sort_keys=True, ensure_ascii=False).replace('</', '<\\/')
    if '__CYCLE_DATA_JSON__' not in template_text:
        raise CycleError('HTML template is missing __CYCLE_DATA_JSON__ placeholder')
    return template_text.replace('__CYCLE_DATA_JSON__', safe_json, 1)


def _validate_consent_flags(parser, argv):
    for argument in argv:
        if argument == '--':
            break
        option = argument.split('=', 1)[0]
        if option == '--dry-run':
            parser.error('--dry-run is retired; omit --apply to preview')
        if option.startswith('--') and len(option) > 2 and '--apply'.startswith(option) and option != '--apply':
            parser.error('mutation consent requires the exact --apply flag')


def _build_parser():
    parser = argparse.ArgumentParser(
        prog='dev_cycle.py',
        description='Record local pre-PR spans, collect GitHub PR/CI timings, analyze long poles, '
                    'and render concise Phase Duration Breakdown HTML reports.',
        allow_abbrev=False,
    )
    commands = parser.add_subparsers(dest='command', required=True, metavar='VERB')

    rec = commands.add_parser('record', help='append local pre-PR phase spans (or import a JSONL work journal)',
                              allow_abbrev=False)
    rec.add_argument('--repo', dest='cycle_repo', required=True, help='repository in owner/name form')
    rec.add_argument('--task', required=True, help='task or branch identifier (e.g. pr-412)')
    rec.add_argument('--pr', type=int, help='optional pull request number')
    rec.add_argument('--phase', choices=PHASES, help='dev-cycle phase')
    rec.add_argument('--label', help='specific step or command label')
    rec.add_argument('--started', help='ISO-8601 timezone-aware start timestamp')
    rec.add_argument('--ended', help='ISO-8601 timezone-aware end timestamp')
    rec.add_argument('--kind', choices=KINDS, help='active, queue, human_wait, or retry')
    rec.add_argument('--status', choices=STATUSES, default='passed', help='span outcome')
    rec.add_argument('--subsystem', help='affected subsystem or directory')
    rec.add_argument('--warm', choices=WARM_VALUES, help='warm or cold build state')
    rec.add_argument('--commit', help='tested commit SHA')
    rec.add_argument('--note', help='short diagnostic note')
    rec.add_argument('--from-journal', help='import spans from a JSONL work journal directory or events.jsonl')
    rec.add_argument('--store', help='JSONL ledger path (default ~/.local/state/dev-cycle/cycles.jsonl)')
    rec.add_argument('--apply', action='store_true', help='authorize writing to the ledger; otherwise preview')

    col = commands.add_parser('collect', help='collect single-PR or aggregate GitHub PR/CI timings via gh api',
                              allow_abbrev=False)
    col.add_argument('--repo', dest='cycle_repo', required=True, help='repository in owner/name form')
    col.add_argument('--pr', type=int, help='collect a single pull request number')
    col.add_argument('--since', help='collect merged PRs since window (e.g. 30d, 14d, 2026-11-01)')
    col.add_argument('--limit', type=int, default=30, help='maximum merged PRs to collect (default 30)')
    col.add_argument('--store', help='JSONL ledger path')
    col.add_argument('--gh', help='path to gh executable (default gh)')
    col.add_argument('--apply', action='store_true', help='authorize fetching and appending to the ledger')

    snip = commands.add_parser('pr-snippet', help='print a compact PR-body timing comment from local spans',
                               allow_abbrev=False)
    snip.add_argument('--task', required=True, help='task identifier to export')
    snip.add_argument('--repo', dest='cycle_repo', help='optional repository filter')
    snip.add_argument('--store', help='JSONL ledger path')
    snip.add_argument('--tag', default='dev-cycle', help='HTML comment tag prefix (default dev-cycle)')
    snip.add_argument('--json', action='store_true', help='print JSON wrapper instead of raw HTML comment')

    for verb, summary, need_out in (
            ('analyze', 'analyze single-task or aggregate dev-cycle timings, long poles, and scope baselines', False),
            ('render', 'render a concise Phase Duration Breakdown HTML table from the bundled template', True),
    ):
        sub = commands.add_parser(verb, help=summary, allow_abbrev=False)
        sub.add_argument('--store', help='JSONL ledger path')
        sub.add_argument('--input', help='explicit JSON or JSONL file instead of the ledger')
        sub.add_argument('--repo', dest='cycle_repo', help='filter by owner/name')
        sub.add_argument('--pr', type=int, help='single-PR mode for this pull request number')
        sub.add_argument('--task', help='single-task mode for this task identifier')
        sub.add_argument('--since', help='filter window (e.g. 30d, 60d, 2026-11-01)')
        sub.add_argument('--subsystem', help='filter by subsystem name')
        sub.add_argument('--title', help='custom report title')
        sub.add_argument('--output', required=need_out, help='output file path (requires --apply)')
        sub.add_argument('--apply', action='store_true', help='authorize writing output file; otherwise preview')

    return parser


def run_command(args, *, default_store_fn=default_store, template_text=None, snippet_tag='dev-cycle'):
    if args.command == 'record':
        store = Path(args.store).expanduser() if args.store else default_store_fn()
        if args.from_journal:
            spans = spans_from_journal(args.from_journal, repo=args.cycle_repo, task=args.task,
                                       pr=args.pr, subsystem=args.subsystem)
            records = [{**s, 'schema': SCHEMA_VERSION, 'record_type': 'span'} for s in spans]
        else:
            missing = [flag for flag, val in (('--phase', args.phase), ('--started', args.started),
                                              ('--ended', args.ended)) if not val]
            if missing:
                raise CycleError('missing required options (or use --from-journal): ' + ', '.join(missing))
            span = normalize_span({
                'repo': args.cycle_repo, 'task': args.task, 'pr': args.pr,
                'phase': args.phase, 'label': args.label or args.phase,
                'started_at': args.started, 'ended_at': args.ended,
                'kind': args.kind, 'status': args.status,
                'subsystem': args.subsystem, 'warm': args.warm,
                'source': 'local', 'source_commit': args.commit, 'note': args.note,
            })
            records = [{**span, 'schema': SCHEMA_VERSION, 'record_type': 'span'}]
        if not args.apply:
            print(json.dumps({
                'status': 'planned', 'operation': 'cycle record', 'store': str(store),
                'records_to_append': len(records), 'apply_required': True,
            }, sort_keys=True))
            return 0
        append_records(store, records)
        print(json.dumps({
            'status': 'applied', 'operation': 'cycle record', 'store': str(store),
            'records_appended': len(records),
        }, sort_keys=True))
        return 0

    if args.command == 'collect':
        store = Path(args.store).expanduser() if args.store else default_store_fn()
        if args.pr is None and not args.since:
            raise CycleError('provide either --pr NUMBER or --since WINDOW')
        if not args.apply:
            print(json.dumps({
                'status': 'planned', 'operation': 'cycle collect', 'repo': args.cycle_repo,
                'pr': args.pr, 'since': args.since, 'limit': args.limit,
                'store': str(store), 'apply_required': True,
            }, sort_keys=True))
            return 0
        gh_bin = args.gh or 'gh'
        collected = []
        if args.pr is not None:
            collected.append(collect_pr_cycle(gh_bin, args.cycle_repo, args.pr))
        else:
            since_dt = parse_since(args.since)
            pulls = gh_api_json(gh_bin, f'repos/{args.cycle_repo}/pulls?state=closed&sort=updated&direction=desc&per_page={min(args.limit, 100)}')
            for item in pulls if isinstance(pulls, list) else []:
                if len(collected) >= args.limit:
                    break
                if not isinstance(item, dict) or not item.get('merged_at'):
                    continue
                if since_dt and parse_timestamp(item['merged_at']) < since_dt:
                    continue
                collected.append(collect_pr_cycle(gh_bin, args.cycle_repo, int(item['number'])))
        if collected:
            append_records(store, collected)
        print(json.dumps({
            'status': 'applied', 'operation': 'cycle collect', 'repo': args.cycle_repo,
            'store': str(store), 'collected': len(collected), 'prs': [c['pr'] for c in collected],
        }, sort_keys=True))
        return 0

    if args.command == 'pr-snippet':
        store = Path(args.store).expanduser() if args.store else default_store_fn()
        records = read_records(store)
        matched = []
        repo = args.cycle_repo
        for rec in records:
            if rec.get('record_type') != 'span' or rec.get('task') != args.task:
                continue
            if repo and rec.get('repo') != repo:
                continue
            span = normalize_span(rec)
            if not repo and span.get('repo'):
                repo = span['repo']
            matched.append(span)
        tag = getattr(args, 'tag', None) or snippet_tag
        snippet = format_pr_snippet(repo or 'unknown', args.task, matched, tag=tag)
        if args.json:
            print(json.dumps({'status': 'ok', 'repo': repo or 'unknown', 'task': args.task,
                              'span_count': len(matched), 'snippet': snippet}, sort_keys=True))
        else:
            print(snippet)
        return 0

    source_path = Path(args.input).expanduser() if args.input else (Path(args.store).expanduser() if args.store else default_store_fn())

    if args.command == 'analyze':
        if args.output and not args.apply:
            print(json.dumps({
                'status': 'planned', 'operation': 'cycle analyze --output',
                'target': str(args.output), 'apply_required': True,
            }, sort_keys=True))
            return 0
        records = read_records(source_path)
        report = analyze_records(records, repo=args.cycle_repo, pr=args.pr, task=args.task,
                                 since=args.since, subsystem=args.subsystem, title=args.title)
        encoded = json.dumps(report, indent=2, sort_keys=True) + '\n'
        if args.output:
            atomic_write_text(Path(args.output).expanduser(), encoded)
            print(json.dumps({'status': 'applied', 'mode': report['mode'], 'output': str(args.output),
                              'items': report['summary']['items_count'],
                              'long_poles': report['long_poles'][:3]}, sort_keys=True))
            return 0
        sys.stdout.write(encoded)
        return 0

    if args.command == 'render':
        out_path = Path(args.output).expanduser()
        if not args.apply:
            print(json.dumps({
                'status': 'planned', 'operation': 'cycle render',
                'source': str(source_path), 'output': str(out_path), 'apply_required': True,
            }, sort_keys=True))
            return 0
        records = read_records(source_path)
        report = analyze_records(records, repo=args.cycle_repo, pr=args.pr, task=args.task,
                                 since=args.since, subsystem=args.subsystem, title=args.title)
        html_text = render_html(report, template_text=template_text)
        atomic_write_text(out_path, html_text)
        print(json.dumps({
            'status': 'applied', 'operation': 'cycle render', 'mode': report['mode'],
            'output': str(out_path), 'items': report['summary']['items_count'],
            'long_poles': report['long_poles'][:3],
        }, sort_keys=True))
        return 0

    raise CycleError('unknown command: ' + str(args.command))


def main(argv=None):
    parser = _build_parser()
    raw = sys.argv[1:] if argv is None else list(argv)
    _validate_consent_flags(parser, raw)
    args = parser.parse_args(raw)
    try:
        return run_command(args)
    except CycleError as error:
        sys.stderr.write(f'dev_cycle.py {args.command}: {error}\n')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
