"""Offline tests for plugins/rstack/skills/state-requirements/scripts/render_register.py."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'plugins/rstack/skills/state-requirements/scripts/render_register.py'
FIXTURE = ROOT / 'tests/fixtures/rdocs-register.json'

SPEC = importlib.util.spec_from_file_location('render_register', SCRIPT)
rr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rr)


def minimal_register():
    return {
        'title': 'Sample Register',
        'subtitle': 'Round 1',
        'scope_model': {
            'failure_multiplier': 1.2,
            'reference': 'sample baseline',
            'confidence': 'MEDIUM',
            'human_gates': ['Create OAuth client'],
            'rates': [
                {'name': 'Authoring', 'value': '20 LOC/min', 'evidence': 'ASSUMED'},
            ],
        },
        'sections': [
            {
                'id': 'intent',
                'name': 'Intent',
                'summary': 'Product outcomes.',
                'requirements': [
                    {
                        'id': 'R1',
                        'story': 'Users edit markdown cleanly',
                        'text': 'WYSIWYG markdown editor',
                        'backing': 'USER',
                        'states': 'Editor',
                        'category': 'intent',
                        'status': 'user-specified',
                        'kind': 'assumption',
                    },
                ],
            },
            {
                'id': 'storage',
                'name': 'Storage',
                'summary': 'Durable git store.',
                'requirements': [
                    {
                        'id': 'R2',
                        'story': 'Saves commit atomically to git',
                        'text': 'In-memory git commit',
                        'backing': 'save p95 17ms MEASURED',
                        'states': 'Committed',
                        'category': 'arch',
                        'status': 'validated',
                        'kind': 'implementation',
                        'scope': {
                            'first_pass_min': 30,
                            'depends_on': [],
                            'breakdown': {
                                'edit': {'min': 15, 'why': '300 LOC at 20 LOC/min'},
                                'build_test': {'min': 10, 'why': '3 cycles'},
                                'verify': {'min': 5, 'why': 'benchmark'},
                            },
                            'basis': '300 LOC + tests',
                            'risk': 'Low',
                        },
                    },
                    {
                        'id': 'R3',
                        'story': 'Search indexes committed docs',
                        'text': 'FTS5 upsert on commit',
                        'backing': 'ASSUMED',
                        'states': 'Projected',
                        'category': 'arch',
                        'status': 'unconfirmed',
                        'kind': 'implementation',
                        'scope': {
                            'first_pass_min': 20,
                            'depends_on': ['R2'],
                            'breakdown': {
                                'edit': {'min': 10, 'why': '200 LOC'},
                                'build_test': {'min': 6, 'why': '2 cycles'},
                                'verify': {'min': 4, 'why': 'query check'},
                            },
                            'basis': 'FTS5 index',
                            'risk': 'Tokenizer edge cases',
                        },
                    },
                ],
            },
        ],
    }


class RegisterRendererTests(unittest.TestCase):
    def test_real_rdocs_fixture_validates_schedules_and_renders_cleanly(self):
        reg = json.loads(FIXTURE.read_text(encoding='utf-8'))
        model = rr.validate(reg)
        self.assertEqual(model['active_count'], 49)
        self.assertEqual(model['impl_count'], 32)
        self.assertEqual(model['assumption_count'], 17)
        self.assertEqual(model['status_counts'], {
            'needs-you': 2,
            'user-specified': 10,
            'validated': 13,
            'unconfirmed': 24,
        })
        self.assertEqual(model['total'], 685)
        self.assertEqual(model['cp'], 260)
        self.assertEqual(model['path'], ["R35'''", "R15'", "R18'''", "R28'''", "R27''", "R55''"])

        with tempfile.TemporaryDirectory() as tmp:
            out_html = Path(tmp) / 'register.html'
            res = subprocess.run(
                [sys.executable, '-B', str(SCRIPT), str(FIXTURE), '--out', str(out_html), '--max-height', '720'],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            body = out_html.read_text(encoding='utf-8')
            self.assertIn('Implementation scope', body)
            self.assertIn('Rates behind every estimate', body)
            self.assertIn('Implementation plan order', body)
            self.assertIn('--rv-max:720px', body)
            self.assertIn('data-kind="implementation"', body)
            self.assertIn('data-kind="assumption"', body)
            self.assertNotIn('Changed this round', body)

            summary = subprocess.run(
                [sys.executable, '-B', str(SCRIPT), str(FIXTURE), '--summary'],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(summary.returncode, 0, summary.stderr)
            self.assertIn('Needs you:', summary.stdout)
            self.assertIn('Unconfirmed on critical path:', summary.stdout)
            self.assertIn('Human gates:', summary.stdout)

    def test_validator_refuses_invalid_registers(self):
        def expect_fail(mutator, fragment):
            reg = minimal_register()
            mutator(reg)
            with self.assertRaisesRegex(rr.RegisterError, fragment):
                rr.validate(reg)

        # Missing story
        expect_fail(lambda r: r['sections'][0]['requirements'][0].pop('story'), 'missing story')
        # Unknown status
        expect_fail(lambda r: r['sections'][0]['requirements'][0].__setitem__('status', 'bogus'), 'unknown status')
        # Unknown kind
        expect_fail(lambda r: r['sections'][0]['requirements'][0].__setitem__('kind', 'other'), 'kind must be')
        # Duplicate ID
        def dup_id(r):
            r['sections'][1]['requirements'].append(copy.deepcopy(r['sections'][0]['requirements'][0]))
        expect_fail(dup_id, 'duplicate requirement id')
        # Implementation missing scope
        expect_fail(lambda r: r['sections'][1]['requirements'][0].pop('scope'), 'needs scope.first_pass_min')
        # Implementation missing basis/risk
        expect_fail(lambda r: r['sections'][1]['requirements'][0]['scope'].pop('risk'), 'needs risk')
        # Breakdown missing why
        expect_fail(lambda r: r['sections'][1]['requirements'][0]['scope']['breakdown']['edit'].pop('why'), 'needs min and why')
        # Breakdown sum mismatch
        expect_fail(lambda r: r['sections'][1]['requirements'][0]['scope'].__setitem__('first_pass_min', 99), 'does not sum')
        # Scope on assumption
        expect_fail(lambda r: r['sections'][0]['requirements'][0].__setitem__('scope', {'first_pass_min': 5}), 'assumptions carry no scope')
        # depends_on referencing an assumption
        expect_fail(lambda r: r['sections'][1]['requirements'][0]['scope'].__setitem__('depends_on', ['R1']), 'not an implementation requirement')
        # Dependency cycle
        expect_fail(lambda r: r['sections'][1]['requirements'][0]['scope'].__setitem__('depends_on', ['R3']), 'dependency cycle')
        # Unknown change tag
        expect_fail(lambda r: r['sections'][0]['requirements'][0].__setitem__('change', 'renamed'), 'unknown change')

    def test_architecture_component_id_validation(self):
        reg = minimal_register()
        # storage matches arch component; intent is a permitted meta section
        res = rr.validate(reg, arch_components={'storage', 'web'})
        self.assertEqual(res['active_count'], 3)

        # Unknown section fails when --arch is provided
        with self.assertRaisesRegex(rr.RegisterError, "section 'storage' does not match"):
            rr.validate(reg, arch_components={'web', 'mcp'})

    def test_round_deltas_filter_and_deleted_exclusion(self):
        reg = minimal_register()
        reg['sections'][1]['requirements'][0]['change'] = 'changed'
        reg['sections'][1]['requirements'][1]['change'] = 'added'
        reg['sections'][1]['requirements'].append({
            'id': 'R9',
            'story': 'Removed custom parser',
            'text': 'Deleted custom parser',
            'backing': 'Replaced by OSS library',
            'states': '—',
            'category': 'arch',
            'status': 'validated',
            'kind': 'implementation',
            'change': 'deleted',
        })
        model = rr.validate(reg)
        # Deleted requirement does not count toward active count or implementation totals
        self.assertEqual(model['active_count'], 3)
        self.assertEqual(model['impl_count'], 2)
        self.assertEqual(model['total'], 50)
        self.assertEqual(model['delta_counts'], {'added': 1, 'changed': 1, 'deleted': 1})

        html_out = rr.render(reg)
        self.assertIn('Changed this round', html_out)
        self.assertIn('data-change="deleted"', html_out)
        self.assertIn('data-change="added"', html_out)
        self.assertIn('data-change="changed"', html_out)


if __name__ == '__main__':
    unittest.main()
