#!/usr/bin/env python3
"""Deterministically validate, generate, and render Mermaid stateDiagram-v2 specs.

Stdlib Python 3.9+ only. Optionally invokes `pele@1.9.0` via Node to render
themeable SVG/HTML (following backnotprop/pstack's statechart renderer).
"""

from __future__ import annotations

import argparse
from collections import deque
import html as html_mod
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

STATE_ID_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
MAX_RECOMMENDED_ARROWS = 20

GROUPS = ('blue', 'orange', 'purple', 'yellow', 'teal', 'tan', 'pink')
HIGHLIGHTS = ('bottleneck', 'breaks', 'mayBreak', 'risk')

PELE_CSS = """
.pele {
  --pele-bg: var(--background, #ffffff);
  --pele-fg: var(--foreground, #1c1c1c);
  --pele-muted: var(--muted-foreground, #656565);
  --pele-line: var(--muted-foreground, #808080);
  --pele-surface: var(--card, #fcfcfc);
  --pele-surface-alt: var(--secondary, #f1f1f1);
  --pele-border: var(--border, #c9c9c9);
}
.pele .blue rect { fill: #c3e0ff; }
.pele .orange rect { fill: #f0d3bf; }
.pele .purple rect { fill: #e3d5ff; }
.pele .yellow rect { fill: #f0dcbf; }
.pele .teal rect { fill: #bfe3df; }
.pele .tan rect { fill: #e5d9ce; }
.pele .pink rect { fill: #ffcbe6; }
.pele .breaks rect, .pele .bottleneck rect {
  fill: #ffecee !important;
  stroke: #e72e3b !important;
  stroke-width: 2.5px !important;
}
.pele .breaks text, .pele .bottleneck text { fill: #cd2834 !important; font-weight: 700; }
.pele .mayBreak rect, .pele .risk rect {
  fill: #fff3e6 !important;
  stroke: #e8730c !important;
  stroke-width: 2.5px !important;
}
.pele .mayBreak text, .pele .risk text { fill: #b85a06 !important; }
@media (prefers-color-scheme: dark) {
  .pele {
    --pele-bg: var(--background, #141820);
    --pele-fg: var(--foreground, #f5f5f5);
    --pele-muted: var(--muted-foreground, #acacac);
    --pele-line: var(--muted-foreground, #939393);
    --pele-surface: var(--card, #1b2230);
    --pele-surface-alt: var(--secondary, #263042);
    --pele-border: var(--border, #435066);
  }
  .pele .blue rect { fill: #1b3857; }
  .pele .orange rect { fill: #573117; }
  .pele .purple rect { fill: #3c2e57; }
  .pele .yellow rect { fill: #573d17; }
  .pele .teal rect { fill: #174641; }
  .pele .tan rect { fill: #3d3127; }
  .pele .pink rect { fill: #57233e; }
  .pele .breaks rect, .pele .bottleneck rect {
    fill: #2e2021 !important;
    stroke: #cf2b35 !important;
  }
  .pele .breaks text, .pele .bottleneck text { fill: #ff6463 !important; }
  .pele .mayBreak rect, .pele .risk rect {
    fill: #2e2619 !important;
    stroke: #d0700f !important;
  }
  .pele .mayBreak text, .pele .risk text { fill: #ffa257 !important; }
}
""".strip()


class DiagramError(ValueError):
    """Invalid state machine specification or diagram syntax."""


def _clean_text(value):
    return str(value).replace('\n', ' ').replace('"', "'").strip()


def validate_spec(spec):
    if not isinstance(spec, dict):
        raise DiagramError('spec must be a JSON object')
    states = spec.get('states')
    transitions = spec.get('transitions')
    if not isinstance(states, list) or not states:
        raise DiagramError('spec requires a non-empty states list')
    if not isinstance(transitions, list) or not transitions:
        raise DiagramError('spec requires a non-empty transitions list')

    errors = []
    warnings = []
    by_id = {}
    for entry in states:
        if not isinstance(entry, dict):
            errors.append('every state entry must be an object')
            continue
        sid = entry.get('id')
        if not isinstance(sid, str) or not STATE_ID_RE.match(sid):
            errors.append(f'invalid state id: {sid!r}')
            continue
        if sid in by_id:
            errors.append(f'duplicate state id: {sid}')
            continue
        group = entry.get('group')
        if group is not None and group not in GROUPS:
            errors.append(f'state {sid}: unsupported group {group!r}')
        highlight = entry.get('highlight')
        if highlight is not None and highlight not in HIGHLIGHTS:
            errors.append(f'state {sid}: unsupported highlight {highlight!r}')
        by_id[sid] = entry

    outgoing = {sid: [] for sid in by_id}
    starts = []
    for idx, tr in enumerate(transitions, 1):
        if not isinstance(tr, dict):
            errors.append(f'transition #{idx} must be an object')
            continue
        src = tr.get('from')
        dst = tr.get('to')
        if src != '[*]' and src not in by_id:
            errors.append(f'transition #{idx} references unknown source state: {src!r}')
        if dst != '[*]' and dst not in by_id:
            errors.append(f'transition #{idx} references unknown target state: {dst!r}')
        if src == '[*]' and dst in by_id:
            starts.append(dst)
        elif src in by_id:
            outgoing[src].append(dst)

    if not starts:
        errors.append('spec must include at least one transition from "[*]"')

    # Reachability BFS
    reachable = set()
    queue = deque(starts)
    while queue:
        cur = queue.popleft()
        if cur in reachable:
            continue
        reachable.add(cur)
        for nxt in outgoing.get(cur, ()):
            if nxt in by_id and nxt not in reachable:
                queue.append(nxt)
    unreachable = sorted(set(by_id) - reachable)
    if unreachable:
        errors.append('unreachable states: ' + ', '.join(unreachable))

    # Non-terminal deadlock check
    dead_ends = sorted(
        sid for sid, entry in by_id.items()
        if not outgoing.get(sid) and not entry.get('final')
    )
    if dead_ends:
        errors.append('non-final states without outgoing transitions: ' + ', '.join(dead_ends))

    if len(transitions) > MAX_RECOMMENDED_ARROWS:
        warnings.append(
            f'{len(transitions)} transitions exceeds recommended readability budget of {MAX_RECOMMENDED_ARROWS}'
        )

    if errors:
        raise DiagramError('; '.join(errors))
    return {'states': len(by_id), 'transitions': len(transitions), 'warnings': warnings}


def _format_transition_label(tr):
    parts = []
    if tr.get('event'):
        parts.append(_clean_text(tr['event']))
    if tr.get('guard'):
        parts.append('[' + _clean_text(tr['guard']) + ']')
    if tr.get('action'):
        parts.append('/ ' + _clean_text(tr['action']))
    if tr.get('metric'):
        parts.append('(' + _clean_text(tr['metric']) + ')')
    return ' '.join(parts)


def emit_mermaid(spec):
    validate_spec(spec)
    lines = ['stateDiagram-v2']
    if spec.get('title'):
        lines.append('    %% title: ' + _clean_text(spec['title']))

    # Emit states (grouped by region if regions are used, otherwise flat/ordered)
    regions = {}
    plain_states = []
    for entry in spec['states']:
        region = entry.get('region')
        if region:
            regions.setdefault(str(region), []).append(entry)
        else:
            plain_states.append(entry)

    def format_state_decl(entry, indent='    '):
        sid = entry['id']
        label = _clean_text(entry.get('label') or sid)
        metrics = entry.get('metrics') or []
        if isinstance(metrics, str):
            metrics = [metrics]
        if metrics:
            metric_str = ', '.join(_clean_text(m) for m in metrics if str(m).strip())
            full = f'{label} [{metric_str}]' if metric_str else label
        else:
            full = label
        if full != sid:
            return f'{indent}state "{full}" as {sid}'
        return None

    for entry in plain_states:
        decl = format_state_decl(entry)
        if decl:
            lines.append(decl)

    if regions:
        parent_id = re.sub(r'[^A-Za-z0-9_]', '_', str(spec.get('parallel_group') or 'Concurrent'))
        lines.append(f'    state {parent_id} {{')
        region_names = list(regions.keys())
        for r_idx, r_name in enumerate(region_names):
            for entry in regions[r_name]:
                decl = format_state_decl(entry, indent='        ')
                if decl:
                    lines.append(decl)
            if r_idx + 1 < len(region_names):
                lines.append('        --')
        lines.append('    }')

    lines.append('')
    for tr in spec['transitions']:
        label = _format_transition_label(tr)
        if label:
            lines.append(f'    {tr["from"]} --> {tr["to"]} : {label}')
        else:
            lines.append(f'    {tr["from"]} --> {tr["to"]}')

    # Emit Mermaid classDef + class assignments for highlights & groups
    class_lines = []
    used_highlights = set()
    for entry in spec['states']:
        if entry.get('group'):
            class_lines.append(f'    class {entry["id"]} {entry["group"]}')
        if entry.get('highlight'):
            used_highlights.add(entry['highlight'])
            class_lines.append(f'    class {entry["id"]} {entry["highlight"]}')
    if used_highlights or class_lines:
        lines.append('')
        if 'breaks' in used_highlights or 'bottleneck' in used_highlights:
            lines.append('    classDef bottleneck fill:#ffecee,stroke:#e72e3b,stroke-width:2px,color:#cd2834')
            lines.append('    classDef breaks fill:#ffecee,stroke:#e72e3b,stroke-width:2px,color:#cd2834')
        if 'risk' in used_highlights or 'mayBreak' in used_highlights:
            lines.append('    classDef risk fill:#fff3e6,stroke:#e8730c,stroke-width:2px,color:#b85a06')
            lines.append('    classDef mayBreak fill:#fff3e6,stroke:#e8730c,stroke-width:2px,color:#b85a06')
        lines.extend(class_lines)

    return '\n'.join(lines) + '\n'


def validate_mermaid(text):
    raw_lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith('%%')]
    if not raw_lines or not raw_lines[0].startswith('stateDiagram-v2'):
        raise DiagramError('diagram must begin with stateDiagram-v2')
    depth = 0
    arrow_count = 0
    has_start = False
    for idx, line in enumerate(raw_lines[1:], 2):
        depth += line.count('{') - line.count('}')
        if depth < 0:
            raise DiagramError(f'line {idx}: unmatched closing brace')
        if '-->' in line:
            arrow_count += 1
            left, right = line.split('-->', 1)
            if left.strip() == '[*]':
                has_start = True
            if not left.strip() or not right.strip():
                raise DiagramError(f'line {idx}: malformed transition')
    if depth != 0:
        raise DiagramError('unclosed composite state block')
    if arrow_count == 0:
        raise DiagramError('diagram has no transitions')
    warnings = []
    if not has_start:
        warnings.append('diagram has no [*] start transition')
    if arrow_count > MAX_RECOMMENDED_ARROWS:
        warnings.append(f'{arrow_count} transitions exceeds recommended readability budget of {MAX_RECOMMENDED_ARROWS}')
    return {'status': 'passed', 'transitions': arrow_count, 'warnings': warnings}


def render_svg_with_pele(mermaid_text, *, node_bin='node', pele_module='pele'):
    script = (
        'import { createRequire } from "node:module";\n'
        'const fs = await import("node:fs");\n'
        'const input = fs.readFileSync(0, "utf8");\n'
        f'const mod = await import({json.dumps(pele_module)});\n'
        'const render = mod.render || (mod.default && mod.default.render);\n'
        'if (typeof render !== "function") { throw new Error("pele render() export not found"); }\n'
        'const svg = await render(input, { limit: 1_000_000, outputLimit: 8_000_000, maxEdges: 10_000 });\n'
        'process.stdout.write(typeof svg === "string" ? svg : (svg && svg.svg ? svg.svg : String(svg)));\n'
    )
    proc = subprocess.run([node_bin, '--input-type=module', '-e', script],
                          input=mermaid_text, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise DiagramError('pele render failed: ' + (proc.stderr.strip() or f'exit {proc.returncode}'))
    svg = proc.stdout.strip()
    if '<svg' not in svg:
        raise DiagramError('pele did not return SVG output')
    # Inject light/dark Pele CSS into the SVG root.
    style_tag = f'<style>{PELE_CSS}</style>'
    return re.sub(r'(<svg\b[^>]*>)', r'\1' + style_tag, svg, count=1)


def wrap_html(title, *, svg=None, mermaid_text=None):
    safe_title = html_mod.escape(title or 'State Machine Diagram')
    if svg is not None:
        body = f'<div class="diagram-svg">{svg}</div>'
    else:
        body = f'<pre class="diagram-mmd">{html_mod.escape(mermaid_text or "")}</pre>'
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f'<title>{safe_title}</title>\n<style>\n'
        'body{margin:0;color:var(--foreground,#1c1c1c);font:13px/1.45 var(--font-sans,ui-sans-serif,system-ui,sans-serif)}\n'
        'h1{margin:0 0 8px;font-size:15px;font-weight:650}\n'
        '.diagram-svg svg{max-width:100%;height:auto;display:block}\n'
        '.diagram-mmd{margin:0;padding:12px;border:1px solid var(--border,#d7e0ec);border-radius:var(--radius,8px);overflow:auto;font:12px/1.5 var(--font-mono,ui-monospace,monospace)}\n'
        f'{PELE_CSS}\n</style>\n</head>\n<body>\n<h1>{safe_title}</h1>\n{body}\n</body>\n</html>\n'
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='command', required=True)

    b = sub.add_parser('build', help='validate a JSON spec and emit Mermaid stateDiagram-v2 (and optional SVG/HTML)')
    b.add_argument('spec', type=Path, help='path to JSON state-machine spec')
    b.add_argument('--out-mmd', type=Path, help='write canonical Mermaid output')
    b.add_argument('--out-svg', type=Path, help='render SVG via pele@1.9.0')
    b.add_argument('--out-html', type=Path, help='render self-contained HTML (uses pele SVG when available)')
    b.add_argument('--node', default='node', help='node executable (default node)')
    b.add_argument('--pele-module', default='pele', help='ESM module specifier for pele (default pele)')

    v = sub.add_parser('validate', help='validate a Mermaid stateDiagram-v2 file')
    v.add_argument('diagram', type=Path, help='path to .mmd file')

    args = parser.parse_args()
    try:
        if args.command == 'validate':
            result = validate_mermaid(args.diagram.read_text(encoding='utf-8'))
            print(json.dumps(result, sort_keys=True))
            return 0
        spec = json.loads(args.spec.read_text(encoding='utf-8'))
        summary = validate_spec(spec)
        mermaid_text = emit_mermaid(spec)
        if args.out_mmd:
            args.out_mmd.parent.mkdir(parents=True, exist_ok=True)
            args.out_mmd.write_text(mermaid_text, encoding='utf-8')
        svg_text = None
        render_mode = 'mermaid'
        if args.out_svg or args.out_html:
            if shutil.which(args.node) or Path(args.node).is_file():
                try:
                    svg_text = render_svg_with_pele(mermaid_text, node_bin=args.node, pele_module=args.pele_module)
                    render_mode = 'pele-svg'
                except DiagramError:
                    if args.out_svg:
                        raise
            elif args.out_svg:
                raise DiagramError('node executable not found for --out-svg')
        if args.out_svg:
            args.out_svg.parent.mkdir(parents=True, exist_ok=True)
            args.out_svg.write_text(svg_text, encoding='utf-8')
        if args.out_html:
            args.out_html.parent.mkdir(parents=True, exist_ok=True)
            args.out_html.write_text(
                wrap_html(spec.get('title') or 'State Machine Diagram', svg=svg_text, mermaid_text=mermaid_text),
                encoding='utf-8',
            )
        output = {'status': 'passed', 'render_mode': render_mode, **summary}
        if not args.out_mmd and not args.out_svg and not args.out_html:
            sys.stdout.write(mermaid_text)
        else:
            print(json.dumps(output, sort_keys=True))
        return 0
    except (DiagramError, OSError, json.JSONDecodeError) as error:
        sys.stderr.write(f'state_diagram.py: {error}\n')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
