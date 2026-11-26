#!/usr/bin/env python3
"""Deterministically validate, generate, and render system diagrams.

Supports two modes from JSON specs (and validates raw .mmd files):
- `architecture`: Mermaid `flowchart` with `subgraph` boundaries, component shapes,
  protocols and metrics on edges, connectivity checks, and edge budgets.
- `flow`: Mermaid `stateDiagram-v2` for lifecycles, request paths, workflows, and
  dev cycles, with reachability, non-terminal deadlock, and arrow-budget checks.

Stdlib Python 3.9+ only. Optionally invokes `pele@1.9.0` via Node to render
themeable light/dark SVG and self-contained HTML.
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

NODE_ID_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_-]*$')
STATE_ID_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
MAX_FLOW_ARROWS = 20
MAX_ARCH_EDGES = 25

GROUPS = ('blue', 'orange', 'purple', 'yellow', 'teal', 'tan', 'pink')
HIGHLIGHTS = ('bottleneck', 'breaks', 'mayBreak', 'risk')
ARCH_SHAPES = ('service', 'store', 'client', 'external', 'gate')
ARCH_EDGE_KINDS = ('normal', 'async', 'dashed')
ARCH_DIRECTIONS = ('LR', 'TB', 'RL', 'BT')

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
.pele .blue rect, .pele .blue path { fill: #c3e0ff; }
.pele .orange rect, .pele .orange path { fill: #f0d3bf; }
.pele .purple rect, .pele .purple path { fill: #e3d5ff; }
.pele .yellow rect, .pele .yellow path { fill: #f0dcbf; }
.pele .teal rect, .pele .teal path { fill: #bfe3df; }
.pele .tan rect, .pele .tan path { fill: #e5d9ce; }
.pele .pink rect, .pele .pink path { fill: #ffcbe6; }
.pele .breaks rect, .pele .bottleneck rect,
.pele .breaks path, .pele .bottleneck path {
  fill: #ffecee !important;
  stroke: #e72e3b !important;
  stroke-width: 2.5px !important;
}
.pele .breaks text, .pele .bottleneck text { fill: #cd2834 !important; font-weight: 700; }
.pele .mayBreak rect, .pele .risk rect,
.pele .mayBreak path, .pele .risk path {
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
  .pele .blue rect, .pele .blue path { fill: #1b3857; }
  .pele .orange rect, .pele .orange path { fill: #573117; }
  .pele .purple rect, .pele .purple path { fill: #3c2e57; }
  .pele .yellow rect, .pele .yellow path { fill: #573d17; }
  .pele .teal rect, .pele .teal path { fill: #174641; }
  .pele .tan rect, .pele .tan path { fill: #3d3127; }
  .pele .pink rect, .pele .pink path { fill: #57233e; }
  .pele .breaks rect, .pele .bottleneck rect,
  .pele .breaks path, .pele .bottleneck path {
    fill: #2e2021 !important;
    stroke: #cf2b35 !important;
  }
  .pele .breaks text, .pele .bottleneck text { fill: #ff6463 !important; }
  .pele .mayBreak rect, .pele .risk rect,
  .pele .mayBreak path, .pele .risk path {
    fill: #2e2619 !important;
    stroke: #d0700f !important;
  }
  .pele .mayBreak text, .pele .risk text { fill: #ffa257 !important; }
}
""".strip()


class DiagramError(ValueError):
    """Invalid diagram specification or Mermaid syntax."""


def _clean_text(value):
    return str(value).replace('\n', ' ').replace('"', "'").replace('|', '/').strip()


def _mermaid_safe_id(raw_id):
    return re.sub(r'[^A-Za-z0-9_]', '_', str(raw_id))


def detect_mode(spec):
    if not isinstance(spec, dict):
        raise DiagramError('spec must be a JSON object')
    mode = spec.get('mode')
    if mode in ('architecture', 'flow'):
        return mode
    if mode is not None:
        raise DiagramError(f'unsupported diagram mode: {mode!r} (expected architecture or flow)')
    if 'components' in spec or 'edges' in spec:
        return 'architecture'
    if 'states' in spec or 'transitions' in spec:
        return 'flow'
    raise DiagramError('spec must specify mode ("architecture" or "flow") or provide components/states')


def component_ids(spec):
    """Return ordered architecture component IDs (which map to register section IDs)."""
    if detect_mode(spec) != 'architecture':
        raise DiagramError('component_ids() requires an architecture spec')
    return [c['id'] for c in spec.get('components', []) if isinstance(c, dict) and isinstance(c.get('id'), str)]


# ------------------------------------------------------------ architecture mode

def validate_architecture_spec(spec, *, strict_budget=False):
    direction = spec.get('direction', 'LR')
    if direction not in ARCH_DIRECTIONS:
        raise DiagramError(f'invalid direction {direction!r}; expected one of {", ".join(ARCH_DIRECTIONS)}')
    boundaries = spec.get('boundaries') or []
    components = spec.get('components')
    edges = spec.get('edges')
    if not isinstance(boundaries, list):
        raise DiagramError('boundaries must be a list')
    if not isinstance(components, list) or not components:
        raise DiagramError('architecture spec requires a non-empty components list')
    if not isinstance(edges, list) or not edges:
        raise DiagramError('architecture spec requires a non-empty edges list')

    errors = []
    warnings = []
    boundary_ids = {}
    for entry in boundaries:
        if not isinstance(entry, dict):
            errors.append('every boundary entry must be an object')
            continue
        bid = entry.get('id')
        if not isinstance(bid, str) or not NODE_ID_RE.match(bid):
            errors.append(f'invalid boundary id: {bid!r}')
            continue
        if bid in boundary_ids:
            errors.append(f'duplicate boundary id: {bid}')
            continue
        boundary_ids[bid] = entry

    comp_ids = {}
    for entry in components:
        if not isinstance(entry, dict):
            errors.append('every component entry must be an object')
            continue
        cid = entry.get('id')
        if not isinstance(cid, str) or not NODE_ID_RE.match(cid):
            errors.append(f'invalid component id: {cid!r}')
            continue
        if cid in comp_ids:
            errors.append(f'duplicate component id: {cid}')
            continue
        if cid in boundary_ids:
            errors.append(f'component id collides with boundary id: {cid}')
            continue
        b = entry.get('boundary')
        if b is not None and b not in boundary_ids:
            errors.append(f'component {cid}: unknown boundary {b!r}')
        shape = entry.get('shape', 'service')
        if shape not in ARCH_SHAPES:
            errors.append(f'component {cid}: unsupported shape {shape!r}')
        group = entry.get('group')
        if group is not None and group not in GROUPS:
            errors.append(f'component {cid}: unsupported group {group!r}')
        highlight = entry.get('highlight')
        if highlight is not None and highlight not in HIGHLIGHTS:
            errors.append(f'component {cid}: unsupported highlight {highlight!r}')
        comp_ids[cid] = entry

    connected = set()
    for idx, edge in enumerate(edges, 1):
        if not isinstance(edge, dict):
            errors.append(f'edge #{idx} must be an object')
            continue
        src = edge.get('from')
        dst = edge.get('to')
        if src not in comp_ids:
            errors.append(f'edge #{idx} references unknown source component: {src!r}')
        if dst not in comp_ids:
            errors.append(f'edge #{idx} references unknown target component: {dst!r}')
        kind = edge.get('kind', 'normal')
        if kind not in ARCH_EDGE_KINDS:
            errors.append(f'edge #{idx}: unsupported kind {kind!r}')
        if src in comp_ids and dst in comp_ids:
            connected.add(src)
            connected.add(dst)

    disconnected = sorted(set(comp_ids) - connected)
    if disconnected:
        errors.append('disconnected components: ' + ', '.join(disconnected))

    max_edges = int(spec.get('edge_budget', MAX_ARCH_EDGES))
    if len(edges) > max_edges:
        msg = f'{len(edges)} edges exceeds edge budget of {max_edges}'
        if strict_budget:
            errors.append(msg)
        else:
            warnings.append(msg)

    if errors:
        raise DiagramError('; '.join(errors))
    return {
        'mode': 'architecture',
        'boundaries': len(boundary_ids),
        'components': len(comp_ids),
        'edges': len(edges),
        'component_ids': list(comp_ids),
        'warnings': warnings,
    }


def _format_arch_node(entry):
    nid = _mermaid_safe_id(entry['id'])
    label = _clean_text(entry.get('label') or entry['id'])
    metrics = entry.get('metrics') or []
    if isinstance(metrics, str):
        metrics = [metrics]
    if metrics:
        mtxt = ', '.join(_clean_text(m) for m in metrics if str(m).strip())
        if mtxt:
            label = f'{label} [{mtxt}]'
    shape = entry.get('shape', 'service')
    if shape == 'store':
        return f'{nid}[("{label}")]'
    if shape in ('external', 'gate'):
        return f'{nid}(["{label}"])'
    return f'{nid}["{label}"]'


def _format_arch_edge(edge):
    src = _mermaid_safe_id(edge['from'])
    dst = _mermaid_safe_id(edge['to'])
    parts = []
    if edge.get('protocol'):
        parts.append(_clean_text(edge['protocol']))
    if edge.get('label'):
        parts.append(_clean_text(edge['label']))
    text = ': '.join(parts)
    if edge.get('metric'):
        metric = _clean_text(edge['metric'])
        text = f'{text} ({metric})' if text else metric
    arrow = '-.->' if edge.get('kind') in ('async', 'dashed') else '-->'
    if text:
        return f'{src} {arrow}|"{text}"| {dst}'
    return f'{src} {arrow} {dst}'


def emit_architecture_mermaid(spec, *, strict_budget=False):
    validate_architecture_spec(spec, strict_budget=strict_budget)
    direction = spec.get('direction', 'LR')
    lines = [f'flowchart {direction}']
    if spec.get('title'):
        lines.append('    %% title: ' + _clean_text(spec['title']))

    by_boundary = {}
    ungrouped = []
    for comp in spec['components']:
        b = comp.get('boundary')
        if b:
            by_boundary.setdefault(b, []).append(comp)
        else:
            ungrouped.append(comp)

    for b in spec.get('boundaries') or []:
        bid = b['id']
        members = by_boundary.get(bid, [])
        if not members:
            continue
        blabel = _clean_text(b.get('label') or bid)
        lines.append(f'    subgraph {_mermaid_safe_id(bid)}["{blabel}"]')
        for comp in members:
            lines.append('        ' + _format_arch_node(comp))
        lines.append('    end')

    for comp in ungrouped:
        lines.append('    ' + _format_arch_node(comp))

    lines.append('')
    for edge in spec['edges']:
        lines.append('    ' + _format_arch_edge(edge))

    class_lines = []
    used_highlights = set()
    for comp in spec['components']:
        nid = _mermaid_safe_id(comp['id'])
        if comp.get('group'):
            class_lines.append(f'    class {nid} {comp["group"]}')
        if comp.get('highlight'):
            used_highlights.add(comp['highlight'])
            class_lines.append(f'    class {nid} {comp["highlight"]}')
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


# -------------------------------------------------------------------- flow mode

def validate_flow_spec(spec, *, strict_budget=False):
    states = spec.get('states')
    transitions = spec.get('transitions')
    if not isinstance(states, list) or not states:
        raise DiagramError('flow spec requires a non-empty states list')
    if not isinstance(transitions, list) or not transitions:
        raise DiagramError('flow spec requires a non-empty transitions list')

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

    dead_ends = sorted(
        sid for sid, entry in by_id.items()
        if not outgoing.get(sid) and not entry.get('final')
    )
    if dead_ends:
        errors.append('non-final states without outgoing transitions: ' + ', '.join(dead_ends))

    max_arrows = int(spec.get('arrow_budget', MAX_FLOW_ARROWS))
    if len(transitions) > max_arrows:
        msg = f'{len(transitions)} transitions exceeds recommended readability budget of {max_arrows}'
        if strict_budget:
            errors.append(msg)
        else:
            warnings.append(msg)

    if errors:
        raise DiagramError('; '.join(errors))
    return {'mode': 'flow', 'states': len(by_id), 'transitions': len(transitions), 'warnings': warnings}


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


def emit_flow_mermaid(spec, *, strict_budget=False):
    validate_flow_spec(spec, strict_budget=strict_budget)
    lines = ['stateDiagram-v2']
    if spec.get('title'):
        lines.append('    %% title: ' + _clean_text(spec['title']))

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
        parent_id = _mermaid_safe_id(spec.get('parallel_group') or 'Concurrent')
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


def validate_spec(spec, *, strict_budget=False):
    mode = detect_mode(spec)
    if mode == 'architecture':
        return validate_architecture_spec(spec, strict_budget=strict_budget)
    return validate_flow_spec(spec, strict_budget=strict_budget)


def emit_mermaid(spec, *, strict_budget=False):
    mode = detect_mode(spec)
    if mode == 'architecture':
        return emit_architecture_mermaid(spec, strict_budget=strict_budget)
    return emit_flow_mermaid(spec, strict_budget=strict_budget)


# ------------------------------------------------------------ raw .mmd validate

def validate_mermaid(text):
    raw_lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith('%%')]
    if not raw_lines:
        raise DiagramError('diagram is empty')
    header = raw_lines[0]
    if header.startswith('stateDiagram-v2'):
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
        if arrow_count > MAX_FLOW_ARROWS:
            warnings.append(f'{arrow_count} transitions exceeds recommended readability budget of {MAX_FLOW_ARROWS}')
        return {'status': 'passed', 'mode': 'flow', 'transitions': arrow_count, 'warnings': warnings}

    if re.match(r'^(flowchart|graph)\s+(LR|TB|TD|RL|BT)\b', header):
        subgraphs = 0
        edges = 0
        for idx, line in enumerate(raw_lines[1:], 2):
            if line.startswith('subgraph '):
                subgraphs += 1
            elif line == 'end':
                subgraphs -= 1
                if subgraphs < 0:
                    raise DiagramError(f'line {idx}: unmatched end without subgraph')
            if '-->' in line or '-.->' in line or '==>' in line:
                edges += 1
        if subgraphs != 0:
            raise DiagramError('unclosed subgraph block')
        if edges == 0:
            raise DiagramError('architecture flowchart has no edges')
        warnings = []
        if edges > MAX_ARCH_EDGES:
            warnings.append(f'{edges} edges exceeds recommended edge budget of {MAX_ARCH_EDGES}')
        return {'status': 'passed', 'mode': 'architecture', 'edges': edges, 'warnings': warnings}

    raise DiagramError('diagram must begin with flowchart <DIR> or stateDiagram-v2')


# ------------------------------------------------------------------ pele render

def render_svg_with_pele(mermaid_text, *, node_bin='node', pele_module='pele'):
    script = (
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
    style_tag = f'<style>{PELE_CSS}</style>'
    return re.sub(r'(<svg\b[^>]*>)', r'\1' + style_tag, svg, count=1)


def wrap_html(title, *, svg=None, mermaid_text=None):
    safe_title = html_mod.escape(title or 'System Diagram')
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='command', required=True)

    b = sub.add_parser('build', help='validate a JSON spec (architecture or flow) and emit Mermaid / SVG / HTML')
    b.add_argument('spec', type=Path, help='path to JSON diagram spec')
    b.add_argument('--out-mmd', type=Path, help='write canonical Mermaid output')
    b.add_argument('--out-svg', type=Path, help='render SVG via pele@1.9.0')
    b.add_argument('--out-html', type=Path, help='render self-contained HTML (uses pele SVG when available)')
    b.add_argument('--strict-budget', action='store_true', help='fail instead of warning when edge/arrow budget is exceeded')
    b.add_argument('--node', default='node', help='node executable (default node)')
    b.add_argument('--pele-module', default='pele', help='ESM module specifier for pele (default pele)')

    v = sub.add_parser('validate', help='validate a Mermaid flowchart or stateDiagram-v2 file')
    v.add_argument('diagram', type=Path, help='path to .mmd file')

    args = parser.parse_args(argv)
    try:
        if args.command == 'validate':
            result = validate_mermaid(args.diagram.read_text(encoding='utf-8'))
            print(json.dumps(result, sort_keys=True))
            return 0
        spec = json.loads(args.spec.read_text(encoding='utf-8'))
        summary = validate_spec(spec, strict_budget=args.strict_budget)
        mermaid_text = emit_mermaid(spec, strict_budget=args.strict_budget)
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
                wrap_html(spec.get('title') or 'System Diagram', svg=svg_text, mermaid_text=mermaid_text),
                encoding='utf-8',
            )
        output = {'status': 'passed', 'render_mode': render_mode, **summary}
        if not args.out_mmd and not args.out_svg and not args.out_html:
            sys.stdout.write(mermaid_text)
        else:
            print(json.dumps(output, sort_keys=True))
        return 0
    except (DiagramError, OSError, json.JSONDecodeError) as error:
        sys.stderr.write(f'system_diagram.py: {error}\n')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
