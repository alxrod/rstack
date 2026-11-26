"""Offline tests for plugins/rstack/skills/system-diagram/scripts/system_diagram.py."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'plugins/rstack/skills/system-diagram/scripts/system_diagram.py'


class SystemDiagramTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.fake_pele = self.base / 'fake-pele.mjs'
        self.fake_pele.write_text(
            'export async function render(src, opts) {\n'
            '  if ((!src.includes("stateDiagram-v2") && !src.includes("flowchart ")) || opts.limit !== 1000000) {\n'
            '    throw new Error("bad call");\n'
            '  }\n'
            '  return "<svg class=\\"pele\\"><g class=\\"bottleneck\\"><rect/><text>OK</text></g></svg>";\n'
            '}\n'
        )

    def run_script(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args],
                              capture_output=True, text=True, timeout=30)

    def test_architecture_mode_emits_subgraphs_shapes_edge_metrics_and_validates(self):
        spec = {
            'mode': 'architecture',
            'title': 'Docs Platform Architecture',
            'direction': 'LR',
            'boundaries': [
                {'id': 'browser', 'label': 'Browser'},
                {'id': 'server', 'label': 'Server'},
                {'id': 'volume', 'label': 'Volume'},
                {'id': 'third_party', 'label': 'Third Parties'},
            ],
            'components': [
                {'id': 'web', 'label': 'Web Client', 'boundary': 'browser', 'shape': 'client',
                 'group': 'blue', 'metrics': ['bundle < 250KB']},
                {'id': 'mcp', 'label': 'HTTP + MCP', 'boundary': 'server', 'shape': 'service', 'group': 'purple'},
                {'id': 'storage', 'label': 'Git Store', 'boundary': 'volume', 'shape': 'store',
                 'group': 'teal', 'metrics': ['save p95 17ms MEASURED']},
                {'id': 'auth', 'label': 'AuthKit', 'boundary': 'third_party', 'shape': 'external', 'group': 'orange'},
            ],
            'edges': [
                {'from': 'web', 'to': 'mcp', 'protocol': 'HTTPS / SSE', 'metric': '< 300ms p95'},
                {'from': 'mcp', 'to': 'storage', 'protocol': 'in-process', 'label': 'commit'},
                {'from': 'mcp', 'to': 'auth', 'protocol': 'JWKS', 'kind': 'dashed'},
            ],
        }
        spec_path = self.base / 'arch.json'
        spec_path.write_text(json.dumps(spec))
        out_mmd = self.base / 'arch.mmd'
        out_svg = self.base / 'arch.svg'
        out_html = self.base / 'arch.html'

        res = self.run_script('build', str(spec_path), '--out-mmd', str(out_mmd),
                              '--out-svg', str(out_svg), '--out-html', str(out_html),
                              '--pele-module', str(self.fake_pele))
        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)
        self.assertEqual(payload['mode'], 'architecture')
        self.assertEqual(payload['render_mode'], 'pele-svg')
        self.assertEqual(payload['component_ids'], ['web', 'mcp', 'storage', 'auth'])

        mmd = out_mmd.read_text()
        self.assertTrue(mmd.startswith('flowchart LR\n'))
        self.assertIn('subgraph browser["Browser"]', mmd)
        self.assertIn('storage[("Git Store [save p95 17ms MEASURED]")]', mmd)
        self.assertIn('auth(["AuthKit"])', mmd)
        self.assertIn('web -->|"HTTPS / SSE (< 300ms p95)"| mcp', mmd)
        self.assertIn('mcp -.->|"JWKS"| auth', mmd)

        val = self.run_script('validate', str(out_mmd))
        self.assertEqual(val.returncode, 0, val.stderr)
        self.assertEqual(json.loads(val.stdout)['mode'], 'architecture')

    def test_architecture_mode_refuses_disconnected_component_dangling_edge_and_budget_violation(self):
        bad = {
            'mode': 'architecture',
            'boundaries': [{'id': 'server', 'label': 'Server'}],
            'components': [
                {'id': 'api', 'boundary': 'server'},
                {'id': 'db', 'boundary': 'missing_boundary'},
                {'id': 'orphan', 'boundary': 'server'},
            ],
            'edges': [
                {'from': 'api', 'to': 'ghost'},
            ],
        }
        spec_path = self.base / 'bad-arch.json'
        spec_path.write_text(json.dumps(bad))
        res = self.run_script('build', str(spec_path))
        self.assertEqual(res.returncode, 2)
        self.assertIn('unknown boundary', res.stderr)
        self.assertIn('unknown target component', res.stderr)
        self.assertIn('disconnected components: api, db, orphan', res.stderr)

        # Edge budget exceeded fails under --strict-budget.
        noisy = {
            'mode': 'architecture',
            'edge_budget': 1,
            'components': [{'id': 'a'}, {'id': 'b'}, {'id': 'c'}],
            'edges': [{'from': 'a', 'to': 'b'}, {'from': 'b', 'to': 'c'}],
        }
        noisy_path = self.base / 'noisy.json'
        noisy_path.write_text(json.dumps(noisy))
        strict = self.run_script('build', str(noisy_path), '--strict-budget')
        self.assertEqual(strict.returncode, 2)
        self.assertIn('exceeds edge budget', strict.stderr)

    def test_flow_mode_emits_metrics_regions_highlights_and_validates(self):
        spec = {
            'mode': 'flow',
            'title': 'PR Delivery',
            'parallel_group': 'Ready',
            'states': [
                {'id': 'Draft', 'label': 'Draft', 'group': 'blue', 'metrics': ['p50 18m']},
                {'id': 'CIQueue', 'label': 'CI Queue', 'group': 'orange', 'region': 'CI', 'metrics': ['p50 2m 55s']},
                {'id': 'CIRun', 'label': 'CI Checks', 'group': 'orange', 'region': 'CI',
                 'metrics': ['p50 5m 30s', 'p90 6m 48s'], 'highlight': 'bottleneck'},
                {'id': 'Review', 'label': 'Human Review', 'group': 'purple', 'region': 'Review', 'metrics': ['p50 6m 30s']},
                {'id': 'Merged', 'label': 'Merged', 'group': 'teal', 'final': True},
            ],
            'transitions': [
                {'from': '[*]', 'to': 'Draft', 'event': 'open_pr'},
                {'from': 'Draft', 'to': 'CIQueue', 'event': 'mark_ready', 'guard': 'checks pass'},
                {'from': 'Draft', 'to': 'Review', 'event': 'mark_ready'},
                {'from': 'CIQueue', 'to': 'CIRun', 'event': 'runner_assigned', 'metric': 'p50 2m 55s'},
                {'from': 'CIRun', 'to': 'Draft', 'event': 'check_failed', 'action': 'fix'},
                {'from': 'CIRun', 'to': 'Merged', 'event': 'green', 'action': 'squash_merge'},
                {'from': 'Review', 'to': 'Merged', 'event': 'approved'},
                {'from': 'Merged', 'to': '[*]'},
            ],
        }
        spec_path = self.base / 'flow.json'
        spec_path.write_text(json.dumps(spec))
        out_mmd = self.base / 'flow.mmd'
        out_html = self.base / 'flow.html'
        out_svg = self.base / 'flow.svg'

        res = self.run_script('build', str(spec_path), '--out-mmd', str(out_mmd),
                              '--out-svg', str(out_svg), '--out-html', str(out_html),
                              '--pele-module', str(self.fake_pele))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(res.stdout)['mode'], 'flow')
        self.assertIn('CI Checks [p50 5m 30s, p90 6m 48s]', out_mmd.read_text())
        self.assertEqual(json.loads(self.run_script('validate', str(out_mmd)).stdout)['status'], 'passed')

    def test_flow_mode_refuses_unreachable_state_and_non_final_deadlock(self):
        bad = {
            'mode': 'flow',
            'states': [{'id': 'Start'}, {'id': 'Stuck'}, {'id': 'Orphan', 'final': True}],
            'transitions': [{'from': '[*]', 'to': 'Start'}, {'from': 'Start', 'to': 'Stuck'}],
        }
        spec_path = self.base / 'bad-flow.json'
        spec_path.write_text(json.dumps(bad))
        res = self.run_script('build', str(spec_path))
        self.assertEqual(res.returncode, 2)
        self.assertIn('unreachable states: Orphan', res.stderr)
        self.assertIn('non-final states without outgoing transitions: Stuck', res.stderr)


if __name__ == '__main__':
    unittest.main()
