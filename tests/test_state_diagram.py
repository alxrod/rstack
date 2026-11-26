"""Offline tests for plugins/rstack/skills/state-machine-diagram/scripts/state_diagram.py."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'plugins/rstack/skills/state-machine-diagram/scripts/state_diagram.py'


class StateDiagramTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()

    def run_script(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args],
                              capture_output=True, text=True, timeout=30)

    def test_build_emits_metrics_regions_highlights_and_validates(self):
        spec = {
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
        spec_path = self.base / 'spec.json'
        spec_path.write_text(json.dumps(spec))
        out_mmd = self.base / 'diagram.mmd'
        out_html = self.base / 'diagram.html'
        out_svg = self.base / 'diagram.svg'

        fake_pele = self.base / 'fake-pele.mjs'
        fake_pele.write_text(
            'export async function render(src, opts) {\n'
            '  if (!src.includes("stateDiagram-v2") || opts.limit !== 1000000) throw new Error("bad call");\n'
            '  return "<svg class=\\"pele\\"><g class=\\"bottleneck\\"><rect/><text>CIRun</text></g></svg>";\n'
            '}\n'
        )
        res = self.run_script('build', str(spec_path), '--out-mmd', str(out_mmd),
                              '--out-svg', str(out_svg), '--out-html', str(out_html),
                              '--pele-module', str(fake_pele))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(res.stdout)['render_mode'], 'pele-svg')
        self.assertIn('CI Checks [p50 5m 30s, p90 6m 48s]', out_mmd.read_text())
        self.assertEqual(json.loads(self.run_script('validate', str(out_mmd)).stdout)['status'], 'passed')

    def test_refuses_unreachable_state_and_non_final_deadlock(self):
        bad = {
            'states': [{'id': 'Start'}, {'id': 'Stuck'}, {'id': 'Orphan', 'final': True}],
            'transitions': [{'from': '[*]', 'to': 'Start'}, {'from': 'Start', 'to': 'Stuck'}],
        }
        spec_path = self.base / 'bad.json'
        spec_path.write_text(json.dumps(bad))
        res = self.run_script('build', str(spec_path))
        self.assertEqual(res.returncode, 2)
        self.assertIn('unreachable states: Orphan', res.stderr)
        self.assertIn('non-final states without outgoing transitions: Stuck', res.stderr)


if __name__ == '__main__':
    unittest.main()
