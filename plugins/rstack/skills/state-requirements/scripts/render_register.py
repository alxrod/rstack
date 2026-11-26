#!/usr/bin/env python3
"""Validate and render a JSON requirements register into a self-contained HTML view.

Stdlib Python 3.9+ only. No external scripts or fonts. Native <details> provides
zero-JS expand/collapse; a small inline script adds Type (Both / Implementation
in plan order / Assumptions), Status, and optional Changed-this-round filters.

  python3 render_register.py register.json --out register.html [--max-height 720] [--arch arch.json]
  python3 render_register.py register.json --validate-only [--arch arch.json]
  python3 render_register.py register.json --summary
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import sys

# Precedence: needs-you > user-specified > validated > unconfirmed
STATUS = {
    'needs-you': ('Needs you', 'warning'),
    'user-specified': ('User specified', 'primary'),
    'validated': ('Validated', 'success'),
    'unconfirmed': ('Unconfirmed', 'muted'),
}

PHASES = {
    'edit': ('Edit', 'Writing the code and its tests.'),
    'build_test': ('Build & test', 'Compiling and running automated tests until they pass.'),
    'verify': ('Verify', 'Checking the result against the real thing: UI, endpoints, measurements.'),
}

KINDS = {
    'implementation': 'Implementation',
    'assumption': 'Assumptions',
}

CHANGES = {
    'added': ('+ added', 'success'),
    'changed': ('~ changed', 'info'),
    'deleted': ('- deleted', 'destructive'),
}

DEFAULT_META_SECTIONS = frozenset({'intent', 'cross'})

CSS = """
:root{--rv-fg:var(--foreground,#1c1c1c);--rv-muted:var(--muted-foreground,#666);--rv-border:var(--border,#d4d4d4);
--rv-card:var(--card,#fafafa);--rv-hover:var(--secondary,#f1f1f1);--rv-radius:var(--radius,8px);
--rv-warning:var(--warning,#b45309);--rv-destructive:var(--destructive,#c0262d);--rv-info:var(--info,#2563eb);
--rv-success:var(--success,#15803d);--rv-primary:var(--primary,#6d28d9);--rv-mono:var(--font-mono,ui-monospace,monospace)}
@media (prefers-color-scheme:dark){:root{--rv-fg:var(--foreground,#f2f2f2);--rv-muted:var(--muted-foreground,#a3a3a3);
--rv-border:var(--border,#3a3f4b);--rv-card:var(--card,#1b1f27);--rv-hover:var(--secondary,#262b35)}}
.rv{color:var(--rv-fg);font:13px/1.45 var(--font-sans,system-ui,sans-serif)}
.rv.scroll{max-height:var(--rv-max);overflow:auto;padding-right:4px}
.rv h2{font-size:15px;margin:0}.rv .sub{color:var(--rv-muted);font-size:12px;margin:2px 0 10px}
.rv .bar{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
.rv button{font:inherit;font-size:12px;color:var(--rv-fg);background:var(--rv-card);border:1px solid var(--rv-border);
border-radius:999px;padding:2px 10px;cursor:pointer}.rv button[aria-pressed=true]{border-color:var(--rv-fg);font-weight:600}.rv .n{color:var(--rv-muted);font-weight:400}
.rv .attn{border:1px solid var(--rv-border);border-radius:var(--rv-radius);padding:10px 12px;margin-bottom:10px;background:var(--rv-card)}
.rv .attn div{margin:2px 0}.rv .attn b{display:inline-block;min-width:96px}
.rv details.sec{border:1px solid var(--rv-border);border-radius:var(--rv-radius);margin-bottom:8px;background:var(--rv-card)}
.rv details.sec>summary{list-style:none;cursor:pointer;padding:8px 12px;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.rv summary::-webkit-details-marker{display:none}
.rv details.sec>summary::before,.rv details.req>summary::before{content:"\\25B8";color:var(--rv-muted);display:inline-block;width:10px;transition:transform .12s}
.rv details[open]>summary::before{transform:rotate(90deg)}
.rv .name{font-weight:600}.rv .blurb{color:var(--rv-muted);flex:1 1 200px}
.rv .counts{display:flex;gap:4px;flex-wrap:wrap}
.rv .pill{font-size:11px;border-radius:999px;padding:0 7px;border:1px solid currentColor;white-space:nowrap}
.rv .s-warning{color:var(--rv-warning)}.rv .s-destructive{color:var(--rv-destructive)}.rv .s-info{color:var(--rv-info)}
.rv .s-success{color:var(--rv-success)}.rv .s-primary{color:var(--rv-primary)}.rv .s-muted{color:var(--rv-muted)}
.rv .reqs{border-top:1px solid var(--rv-border)}
.rv details.req{border-bottom:1px solid var(--rv-border)}.rv details.req:last-child{border-bottom:0}
.rv details.req>summary{list-style:none;cursor:pointer;display:grid;grid-template-columns:10px 62px 1fr auto auto;gap:8px;
padding:5px 12px;align-items:baseline}.rv details.req>summary:hover{background:var(--rv-hover)}
.rv details.req[data-change=deleted]>summary{opacity:.65}.rv details.req[data-change=deleted] .txt{text-decoration:line-through}
.rv .chg{font-size:10px;border-radius:4px;padding:0 5px;border:1px solid currentColor;margin-left:6px;white-space:nowrap;vertical-align:1px}
.rv .id{font-family:var(--rv-mono);font-size:12px;color:var(--rv-muted)}
.rv .txt{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.rv details.req[open] .txt{white-space:normal}
.rv dl{display:grid;grid-template-columns:72px 1fr;gap:3px 10px;margin:0;padding:4px 12px 10px 92px;font-size:12px}
.rv dt{color:var(--rv-muted)}.rv dd{margin:0}
.rv .hidden{display:none}
.rv .time{margin:0 12px 10px 92px;border:1px solid var(--rv-border);border-radius:6px;padding:8px 10px;font-size:12px}
.rv .time .th{font-weight:600;margin-bottom:2px}.rv .time dl{padding:6px 0 0;grid-template-columns:84px 1fr}
.rv .segs{display:flex;height:10px;margin:8px 0 4px;gap:2px}
.rv .seg{position:relative;cursor:help;outline:none}
.rv .seg:first-child{border-radius:5px 0 0 5px}.rv .seg:last-child{border-radius:0 5px 5px 0}.rv .seg:only-child{border-radius:5px}
.rv .seg:hover,.rv .seg:focus-visible{box-shadow:0 0 0 2px var(--rv-fg);z-index:1}
.rv .edit{background:var(--chart-1,#6d8cff)}.rv .build_test{background:var(--chart-2,#e0a24a)}.rv .verify{background:var(--chart-3,#4fb08a)}
.rv .tip{display:none;position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);
width:max-content;max-width:240px;background:var(--popover,var(--rv-card));color:var(--popover-foreground,var(--rv-fg));
border:1px solid var(--rv-border);border-radius:6px;padding:6px 8px;font-size:11px;line-height:1.35;z-index:5;
box-shadow:0 4px 14px rgba(0,0,0,.18);pointer-events:none}
.rv .tip b{display:block;margin-bottom:2px}
.rv .seg:first-child .tip{left:0;transform:none}.rv .seg:last-child:not(:first-child) .tip{left:auto;right:0;transform:none}
.rv .seg:hover .tip,.rv .seg:focus .tip{display:block}
.rv .legend{color:var(--rv-muted);font-size:11px;display:flex;gap:12px;flex-wrap:wrap}
.rv .lg{display:inline-flex;align-items:center;gap:5px}
.rv .why{display:grid;gap:4px;margin:6px 0 2px}.rv .wrow{display:grid;grid-template-columns:96px 34px 1fr;gap:8px;align-items:baseline}
.rv .wm{font-family:var(--rv-mono);color:var(--rv-muted);text-align:right}
.rv details.rates{margin-top:4px;font-size:12px}.rv details.rates>summary{cursor:pointer;color:var(--rv-muted)}
.rv details.rates dl{padding:4px 0 0;grid-template-columns:170px 1fr}
@media (max-width:520px){.rv .wrow{grid-template-columns:80px 30px 1fr}}.rv .sw{width:8px;height:8px;border-radius:2px;display:inline-block}
@media (max-width:520px){.rv .time{margin-left:12px}}
.rv .chip{font-family:var(--rv-mono);font-size:11px;color:var(--rv-muted);border:1px solid var(--rv-border);border-radius:4px;padding:0 5px;white-space:nowrap}
.rv .chip.cp{color:var(--rv-fg);border-color:var(--rv-fg)}.rv .chip.pre{font-family:inherit}
.rv .scope{border:1px solid var(--rv-border);border-radius:var(--rv-radius);background:var(--rv-card);padding:8px 12px;margin-bottom:10px}
.rv .scope .sub{margin:2px 0 0}
.rv .plan{border:1px solid var(--rv-border);border-radius:var(--rv-radius);background:var(--rv-card)}
.rv .planhead{padding:8px 12px;color:var(--rv-muted);font-size:12px}
.rv details.req.step>summary{grid-template-columns:10px 80px 66px 1fr auto auto}
.rv .when{font-family:var(--rv-mono);font-size:12px;color:var(--rv-muted);white-space:nowrap}
.rv .plan .time,.rv .plan dl{margin-left:12px;padding-left:12px}
@media (max-width:520px){.rv details.req.step>summary{grid-template-columns:10px 60px 1fr auto}.rv details.req.step .id{display:none}}
.rv .filters{display:grid;gap:6px;margin-bottom:10px}.rv .filters .bar{margin:0}
.rv .frow{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.rv .flabel{width:44px;color:var(--rv-muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em}
.rv .segctl{display:inline-flex;border:1px solid var(--rv-border);border-radius:8px;overflow:hidden;background:var(--rv-card)}
.rv .segctl button{border:0;border-radius:0;background:transparent;padding:3px 12px}
.rv .segctl button+button{border-left:1px solid var(--rv-border)}
.rv .segctl button[aria-pressed=true]{background:var(--rv-hover);font-weight:600}
@media (max-width:520px){.rv details.req>summary{grid-template-columns:10px 54px 1fr auto}.rv details.req>summary .pill{display:none}
.rv dl{padding-left:12px}}
"""

JS = """
(()=>{const root=document.currentScript.closest('.rv');let st=null,kd=null,delta=false;
const apply=()=>{const planMode=kd==='implementation'&&!delta;
 root.querySelector('.secs').classList.toggle('hidden',planMode);
 root.querySelector('.plan').classList.toggle('hidden',!planMode);
 root.querySelectorAll('details.req').forEach(r=>{
  const chg=r.dataset.change||'';
  const hide=(delta?!chg:chg==='deleted')||(!!st&&r.dataset.status!==st)||(!!kd&&r.dataset.kind!==kd);
  r.classList.toggle('hidden',hide);
 });
 root.querySelectorAll('details.sec').forEach(s=>{
  const vis=s.querySelectorAll('details.req:not(.hidden)').length;
  s.classList.toggle('hidden',(st||kd||delta)&&!vis);
  s.open=!!(st||kd||delta)&&vis>0;
 });};
root.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{
 root.querySelectorAll('[data-filter]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
 st=b.dataset.filter==='all'?null:b.dataset.filter;apply();});
root.querySelectorAll('[data-kind]').forEach(b=>b.onclick=()=>{
 root.querySelectorAll('[data-kind]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
 kd=b.dataset.kind==='both'?null:b.dataset.kind;apply();});
const db=root.querySelector('[data-delta]');
if(db){db.onclick=()=>{delta=!delta;db.setAttribute('aria-pressed',String(delta));apply();};}
apply();})();
"""


class RegisterError(ValueError):
    """Raised when a requirements register violates schema or scheduling constraints."""


def esc(v):
    return html.escape(str(v or ''))


def pill(status, n=None):
    label, tok = STATUS[status]
    txt = f'{n} {label.lower()}' if n is not None else label
    return f'<span class="pill s-{tok}">{esc(txt)}</span>'


def clock(m):
    return f't+{m // 60}:{m % 60:02d}'


def load_arch_component_ids(arch_path):
    data = json.loads(Path(arch_path).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('components'), list):
        raise RegisterError('architecture spec must be a JSON object with a components list')
    ids = set()
    for comp in data['components']:
        if isinstance(comp, dict) and isinstance(comp.get('id'), str) and comp['id']:
            ids.add(comp['id'])
    if not ids:
        raise RegisterError('architecture spec declares no component IDs')
    return ids


def validate(reg, *, arch_components=None, meta_sections=DEFAULT_META_SECTIONS):
    """Validate register structure, statuses, scopes, dependencies, and optional arch sections.

    Returns computed totals, critical path, finish times, and counts.
    """
    if not isinstance(reg, dict) or not isinstance(reg.get('sections'), list) or not reg['sections']:
        raise RegisterError('register must be a JSON object with a non-empty sections list')

    sections = reg['sections']
    sm = reg.get('scope_model') or {}
    mult = float(sm.get('failure_multiplier', 1.0))
    if mult <= 0:
        raise RegisterError('scope_model.failure_multiplier must be positive')

    allowed_sections = None
    if arch_components is not None:
        allowed_sections = set(arch_components) | set(meta_sections or ())
    elif isinstance(reg.get('architecture_components'), list):
        allowed_sections = set(reg['architecture_components']) | set(meta_sections or ())

    seen_sections = set()
    seen_ids = set()
    all_reqs = []
    active_reqs = []
    for sec in sections:
        if not isinstance(sec, dict) or not sec.get('id') or not sec.get('name'):
            raise RegisterError('every section requires non-empty id and name')
        sid = sec['id']
        if sid in seen_sections:
            raise RegisterError(f'duplicate section id: {sid}')
        seen_sections.add(sid)
        if allowed_sections is not None and sid not in allowed_sections:
            raise RegisterError(
                f'section {sid!r} does not match any architecture component ID '
                f'(allowed: {", ".join(sorted(allowed_sections))})'
            )
        reqs = sec.get('requirements')
        if not isinstance(reqs, list):
            raise RegisterError(f'section {sid}: requirements must be a list')
        for r in reqs:
            if not isinstance(r, dict) or not r.get('id'):
                raise RegisterError(f'section {sid}: every requirement needs an id')
            rid = r['id']
            if rid in seen_ids:
                raise RegisterError(f'duplicate requirement id: {rid}')
            seen_ids.add(rid)
            if not r.get('story'):
                raise RegisterError(f'{rid}: missing story (one-line user-facing behavior)')
            if r.get('status') not in STATUS:
                raise RegisterError(f'{rid}: unknown status {r.get("status")!r}')
            if r.get('kind') not in KINDS:
                raise RegisterError(f'{rid}: kind must be implementation or assumption')
            chg = r.get('change')
            if chg is not None and chg not in CHANGES:
                raise RegisterError(f'{rid}: unknown change {chg!r} (expected added, changed, or deleted)')
            all_reqs.append(r)
            if chg != 'deleted':
                active_reqs.append(r)

    impl = {r['id']: r for r in active_reqs if r['kind'] == 'implementation'}
    for r in active_reqs:
        rid = r['id']
        if r['kind'] == 'assumption':
            if r.get('scope'):
                raise RegisterError(f'{rid}: assumptions carry no scope (they are not work)')
            continue
        sc = r.get('scope')
        if not isinstance(sc, dict) or not sc.get('first_pass_min'):
            raise RegisterError(f'{rid}: implementation requirement needs scope.first_pass_min')
        if type(sc['first_pass_min']) not in (int, float) or sc['first_pass_min'] <= 0:
            raise RegisterError(f'{rid}: scope.first_pass_min must be a positive number')
        for field in ('breakdown', 'basis', 'risk'):
            if not sc.get(field):
                raise RegisterError(f'{rid}: implementation scope needs {field} (the dropdown explains the time)')
        if not isinstance(sc['breakdown'], dict) or not sc['breakdown']:
            raise RegisterError(f'{rid}: scope.breakdown must be a non-empty object')
        total_bd = 0
        for ph, v in sc['breakdown'].items():
            if ph not in PHASES or not isinstance(v, dict) or 'min' not in v or not v.get('why'):
                raise RegisterError(f'{rid}: breakdown.{ph} needs min and why (the justification for the time)')
            if type(v['min']) not in (int, float) or v['min'] < 0:
                raise RegisterError(f'{rid}: breakdown.{ph}.min must be non-negative')
            total_bd += v['min']
        if total_bd != sc['first_pass_min']:
            raise RegisterError(f'{rid}: breakdown ({total_bd}) does not sum to first_pass_min ({sc["first_pass_min"]})')
        deps = sc.get('depends_on', [])
        if not isinstance(deps, list):
            raise RegisterError(f'{rid}: scope.depends_on must be a list')
        for dep in deps:
            if dep not in impl:
                raise RegisterError(f'{rid}: depends_on {dep} is not an implementation requirement')

    finish, prev, state = {}, {}, {}

    def visit(i):
        if state.get(i) == 1:
            raise RegisterError(f'dependency cycle through {i}')
        if i in finish:
            return finish[i]
        state[i] = 1
        deps = impl[i]['scope'].get('depends_on', [])
        start, p = 0, None
        for dep in deps:
            f = visit(dep)
            if f > start:
                start, p = f, dep
        finish[i], prev[i], state[i] = start + impl[i]['scope']['first_pass_min'], p, 2
        return finish[i]

    for i in impl:
        visit(i)

    end = max(finish, key=finish.get) if finish else None
    path = []
    while end:
        path.append(end)
        end = prev[end]
    path.reverse()

    total = sum(r['scope']['first_pass_min'] for r in impl.values())
    cp = finish[path[-1]] if path else 0
    return {
        'total': total,
        'total_adj': round(total * mult),
        'cp': cp,
        'cp_adj': round(cp * mult),
        'path': path,
        'finish': finish,
        'active_count': len(active_reqs),
        'impl_count': len(impl),
        'assumption_count': sum(1 for r in active_reqs if r['kind'] == 'assumption'),
        'delta_counts': {k: sum(1 for r in all_reqs if r.get('change') == k) for k in CHANGES},
        'status_counts': {k: sum(1 for r in active_reqs if r['status'] == k) for k in STATUS},
    }


def attention_summary(reg, *, arch_components=None, meta_sections=DEFAULT_META_SECTIONS):
    """Build the concise plain-text summary for chat (Needs you + critical-path unconfirmed)."""
    model = validate(reg, arch_components=arch_components, meta_sections=meta_sections)
    cp_set = set(model['path'])
    needs_you = []
    cp_unconfirmed = []
    for sec in reg['sections']:
        for r in sec['requirements']:
            if r.get('change') == 'deleted':
                continue
            label = r.get('short') or r['story']
            if r['status'] == 'needs-you':
                needs_you.append(f'{r["id"]} ({sec["name"]}): {label}')
            elif r['status'] == 'unconfirmed' and r['id'] in cp_set:
                cp_unconfirmed.append(f'{r["id"]} ({sec["name"]}): {label}')

    h = lambda m: f'{m / 60:.1f} h'
    lines = [
        f'{reg.get("title", "Requirements")} — {model["active_count"]} active '
        f'({model["impl_count"]} implementation, {model["assumption_count"]} assumptions)',
        f'Scope: {h(model["total"])} agent ({h(model["total_adj"])} adj) · '
        f'critical path {h(model["cp"])} ({h(model["cp_adj"])}): ' + (' -> '.join(model['path']) or 'none'),
    ]
    deltas = model['delta_counts']
    if any(deltas.values()):
        lines.append(f'Round delta: +{deltas["added"]} added, ~{deltas["changed"]} changed, -{deltas["deleted"]} deleted')
    if needs_you:
        lines.append('Needs you:')
        lines.extend(f'  - {item}' for item in needs_you)
    else:
        lines.append('Needs you: none')
    if cp_unconfirmed:
        lines.append('Unconfirmed on critical path:')
        lines.extend(f'  - {item}' for item in cp_unconfirmed)
    gates = (reg.get('scope_model') or {}).get('human_gates') or []
    if gates:
        lines.append('Human gates: ' + '; '.join(str(g) for g in gates))
    return '\n'.join(lines) + '\n'


def render(reg, max_height=None, *, arch_components=None, meta_sections=DEFAULT_META_SECTIONS):
    model = validate(reg, arch_components=arch_components, meta_sections=meta_sections)
    sections = reg['sections']
    sm = reg.get('scope_model') or {}
    mult = float(sm.get('failure_multiplier', 1.0))

    all_reqs = [r for s in sections for r in s['requirements']]
    active_reqs = [r for r in all_reqs if r.get('change') != 'deleted']
    changed_count = sum(1 for r in all_reqs if r.get('change'))

    out = [f'<div class="rv{" scroll" if max_height else ""}"'
           + (f' style="--rv-max:{int(max_height)}px"' if max_height else '') + '>']
    out.append(f'<h2>{esc(reg.get("title", "Requirements"))}</h2>')
    if reg.get('subtitle'):
        out.append(f'<div class="sub">{esc(reg["subtitle"])}</div>')

    h = lambda m: f'{m / 60:.1f} h'
    out.append(
        f'<div class="scope"><b>Implementation scope</b> {h(model["total"])} agent time '
        f'({h(model["total_adj"])} failure-adjusted) · critical path {h(model["cp"])} ({h(model["cp_adj"])}): '
        + (' → '.join(f'<span class="id">{esc(i)}</span>' for i in model['path']) or 'none')
        + (f'<div class="sub">{esc(sm.get("confidence"))} · {esc(sm.get("reference"))}</div>' if sm else '')
        + ('<details class="rates"><summary>Rates behind every estimate</summary><dl>'
           + ''.join(f'<dt>{esc(x["name"])}</dt><dd><b>{esc(x["value"])}</b> · {esc(x["evidence"])}</dd>'
                     for x in sm.get('rates', []))
           + '</dl></details>' if sm.get('rates') else '')
        + '</div>'
    )

    tabs = [('all', 'All', len(active_reqs))] + [
        (k, STATUS[k][0], sum(r['status'] == k for r in active_reqs)) for k in STATUS
    ]
    kinds = [('both', 'Both', len(active_reqs))] + [
        (k, v, sum(r['kind'] == k for r in active_reqs)) for k, v in KINDS.items()
    ]
    btn = lambda attr, k, label, n, on: (
        f'<button {attr}="{k}" aria-pressed="{str(on).lower()}">'
        f'{esc(label)} <span class="n">{n}</span></button>'
    )
    delta_btn = (
        f'<button data-delta="1" aria-pressed="false">Changed this round '
        f'<span class="n">{changed_count}</span></button>'
        if changed_count else ''
    )
    out.append(
        '<div class="filters">'
        '<div class="frow"><span class="flabel">Type</span><div class="segctl" role="radiogroup">'
        + ''.join(btn('data-kind', k, label, n, k == 'both') for k, label, n in kinds)
        + '</div>' + delta_btn + '</div>'
        '<div class="frow"><span class="flabel">Status</span><div class="bar" role="tablist">'
        + ''.join(btn('data-filter', k, label, n, k == 'all') for k, label, n in tabs)
        + '</div></div></div>'
    )

    def req_parts(r, section_name):
        time_html = ''
        is_deleted = r.get('change') == 'deleted'
        if r['kind'] == 'implementation' and not is_deleted:
            sc = r['scope']
            m = sc['first_pass_min']
            on_cp = r['id'] in model['path']
            bd = sc['breakdown']
            bar = ''.join(
                f'<span class="seg {k}" tabindex="0" style="flex:{v["min"]}" '
                f'aria-label="{esc(PHASES[k][0])} {v["min"]} min">'
                f'<span class="tip"><b>{esc(PHASES[k][0])} · {v["min"]} min</b>{esc(v["why"])}</span></span>'
                for k, v in bd.items() if v['min']
            )
            deps = ', '.join(sc.get('depends_on', [])) or 'nothing (can start first)'
            start = model['finish'][r['id']] - m
            time_html = (
                '<div class="time"><div class="th">Time</div>'
                f'<div class="est"><b>{m} min</b> first-pass · {round(m * mult)} min failure-adjusted'
                f' · earliest start {clock(start)}' + (' · <b>on critical path</b>' if on_cp else '') + '</div>'
                f'<div class="segs">{bar}</div><div class="why">'
                + ''.join(
                    f'<div class="wrow"><span class="lg"><i class="sw {k}"></i>{esc(PHASES[k][0])}</span>'
                    f'<span class="wm">{v["min"]}m</span><span>{esc(v["why"])}</span></div>'
                    for k, v in bd.items()
                )
                + '</div>'
                f'<dl><dt>Work</dt><dd>{esc(sc["basis"])}</dd><dt>Risk</dt><dd>{esc(sc["risk"])}</dd>'
                f'<dt>Starts after</dt><dd>{esc(deps)}</dd></dl></div>'
            )
            chip = f'<span class="chip{" cp" if on_cp else ""}">{m}m</span>'
        elif is_deleted:
            chip = '<span class="chip pre">deleted</span>'
        else:
            chip = '<span class="chip pre">assumption</span>'

        rows = [
            ('Technical', r.get('text')),
            ('Component', section_name),
            ('Evidence', r.get('backing')),
            ('States', r.get('states')),
            ('Category', r.get('category')),
        ]
        if r['kind'] == 'assumption':
            rows.insert(1, ('Time', 'None: an assumption informs design and is not work'))
        body = (
            '<dl>'
            + ''.join(f'<dt>{esc(k)}</dt><dd>{esc(v)}</dd>' for k, v in rows if v and v != '—')
            + '</dl>'
            + time_html
        )
        chg = r.get('change')
        chg_badge = (
            f'<span class="chg s-{CHANGES[chg][1]}">{esc(CHANGES[chg][0])}</span>'
            if chg else ''
        )
        chg_attr = f' data-change="{esc(chg)}"' if chg else ''
        hidden_cls = ' hidden' if is_deleted else ''
        attrs = f'data-status="{esc(r["status"])}" data-kind="{r["kind"]}"{chg_attr}'
        return attrs, hidden_cls, chip, chg_badge, body

    out.append('<div class="secs">')
    impl_rows = []
    for s in sections:
        reqs = s['requirements']
        counts = {}
        for r in reqs:
            if r.get('change') != 'deleted':
                counts[r['status']] = counts.get(r['status'], 0) + 1
        open_attr = ' open' if s.get('open') else ''
        out.append(
            f'<details class="sec"{open_attr}><summary><span class="name">{esc(s["name"])}</span>'
            f'<span class="blurb">{esc(s.get("summary"))}</span><span class="counts">'
            + ''.join(pill(k, counts[k]) for k in STATUS if k in counts)
            + '</span></summary><div class="reqs">'
        )
        for r in reqs:
            attrs, hidden_cls, chip, chg_badge, body = req_parts(r, s['name'])
            out.append(
                f'<details class="req{hidden_cls}" {attrs}><summary><span class="id">{esc(r["id"])}</span>'
                f'<span class="txt">{esc(r["story"])}{chg_badge}</span>{chip}{pill(r["status"])}'
                f'</summary>{body}</details>'
            )
            if r['kind'] == 'implementation' and r.get('change') != 'deleted':
                impl_rows.append((r, s['name'], attrs, chip, chg_badge, body))
        out.append('</div></details>')
    out.append('</div>')

    # Implementation plan order: earliest start, critical path first among ties, then register order.
    order = {r['id']: i for i, (r, *_rest) in enumerate(impl_rows)}
    impl_rows.sort(key=lambda x: (
        model['finish'][x[0]['id']] - x[0]['scope']['first_pass_min'],
        x[0]['id'] not in model['path'],
        order[x[0]['id']],
    ))
    out.append(
        '<div class="plan hidden"><div class="planhead">Implementation plan order · start times assume every '
        'dependency finishes first; rows with the same start can run in parallel</div><div class="reqs">'
    )
    for n, (r, _sname, attrs, chip, chg_badge, body) in enumerate(impl_rows, 1):
        start = model['finish'][r['id']] - r['scope']['first_pass_min']
        out.append(
            f'<details class="req step" {attrs}><summary><span class="when">{n}. {clock(start)}</span>'
            f'<span class="id">{esc(r["id"])}</span><span class="txt">{esc(r["story"])}{chg_badge}</span>'
            f'{chip}{pill(r["status"])}</summary>{body}</details>'
        )
    out.append('</div></div>')
    out.append(f'<script>{JS}</script></div>')
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<style>{CSS}</style></head><body>'
        + '\n'.join(out)
        + '</body></html>\n'
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    ap.add_argument('register', type=Path, help='path to JSON requirements register')
    ap.add_argument('--out', type=Path, help='output HTML path')
    ap.add_argument('--max-height', type=int, help='optional max height in px for scrollable inline frames')
    ap.add_argument('--arch', type=Path, help='optional architecture diagram JSON spec to validate section IDs against')
    ap.add_argument('--meta-sections', default='intent,cross',
                    help='comma-separated non-component meta section IDs permitted with --arch (default intent,cross)')
    ap.add_argument('--validate-only', action='store_true', help='validate and print JSON metrics without writing HTML')
    ap.add_argument('--summary', action='store_true', help='print concise plain-text attention summary to stdout')
    args = ap.parse_args(argv)

    try:
        reg = json.loads(args.register.read_text(encoding='utf-8'))
        arch_ids = load_arch_component_ids(args.arch) if args.arch else None
        meta = {s.strip() for s in args.meta_sections.split(',') if s.strip()}
        if args.validate_only:
            result = validate(reg, arch_components=arch_ids, meta_sections=meta)
            print(json.dumps({'status': 'passed', **result}, sort_keys=True))
            return 0
        if args.summary:
            sys.stdout.write(attention_summary(reg, arch_components=arch_ids, meta_sections=meta))
            if not args.out:
                return 0
        if not args.out:
            ap.error('--out is required unless --validate-only or --summary is used')
        rendered = render(reg, args.max_height, arch_components=arch_ids, meta_sections=meta)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding='utf-8')
        print(args.out)
        return 0
    except (RegisterError, OSError, json.JSONDecodeError) as error:
        sys.stderr.write(f'render_register.py: {error}\n')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
