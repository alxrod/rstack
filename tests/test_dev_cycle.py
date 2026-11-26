"""Offline tests for standalone plugins/rstack/skills/measure-dev-cycle/scripts/dev_cycle.py."""

import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'plugins/rstack/skills/measure-dev-cycle/scripts/dev_cycle.py'
CLI = [sys.executable, '-B', str(SCRIPT)]


def make_fake_gh(directory, routes):
    data_path = directory / 'fake-gh-routes.json'
    data_path.write_text(json.dumps(routes))
    script = directory / 'fake-gh'
    script.write_text(
        f'#!{sys.executable}\n'
        'import json, sys\n'
        f'routes = json.loads(open({str(data_path)!r}).read())\n'
        'if len(sys.argv) < 3 or sys.argv[1] != "api":\n'
        '    sys.stderr.write("unexpected gh invocation: " + repr(sys.argv) + "\\n")\n'
        '    raise SystemExit(2)\n'
        'endpoint = sys.argv[2]\n'
        'if endpoint not in routes:\n'
        '    sys.stderr.write("missing fake route: " + endpoint + "\\n")\n'
        '    raise SystemExit(1)\n'
        'print(json.dumps(routes[endpoint]))\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


class StandaloneDevCycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.store = self.base / 'state/cycles.jsonl'

    def run_cli(self, *args):
        return subprocess.run([*CLI, *args], cwd=ROOT, capture_output=True, text=True, timeout=60)

    def test_mutating_verbs_preview_by_default_and_refuse_retired_flags(self):
        out_html = self.base / 'out/breakdown.html'
        out_json = self.base / 'out/report.json'
        for args in (
            ('record', '--repo', 'acme/app', '--task', 't1', '--phase', 'compile',
             '--started', '2026-11-25T10:00:00Z', '--ended', '2026-11-25T10:02:00Z', '--store', str(self.store)),
            ('collect', '--repo', 'acme/app', '--pr', '42', '--gh', '/nonexistent/gh', '--store', str(self.store)),
            ('render', '--store', str(self.store), '--output', str(out_html)),
            ('analyze', '--store', str(self.store), '--output', str(out_json)),
        ):
            res = self.run_cli(*args)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(json.loads(res.stdout)['status'], 'planned')
            self.assertFalse(self.store.exists())
            self.assertFalse(out_html.exists())
            self.assertFalse(out_json.exists())
            for bad in ('--dry-run', '--app'):
                rej = self.run_cli(*args, bad)
                self.assertEqual(rej.returncode, 2)

    def test_pr_snippet_collect_aggregate_and_concise_html_render(self):
        for phase, label, start, end in (
            ('edit', 'implement feature', '2026-11-25T17:00:00Z', '2026-11-25T17:12:00Z'),
            ('test', 'unit tests', '2026-11-25T17:12:00Z', '2026-11-25T17:14:30Z'),
        ):
            res = self.run_cli(
                'record', '--apply', '--repo', 'acme/app', '--task', 'pr-191', '--pr', '191',
                '--phase', phase, '--label', label, '--started', start, '--ended', end,
                '--store', str(self.store),
            )
            self.assertEqual(res.returncode, 0, res.stderr)

        snip = self.run_cli('pr-snippet', '--task', 'pr-191', '--store', str(self.store))
        self.assertEqual(snip.returncode, 0, snip.stderr)
        snippet = snip.stdout.strip()
        self.assertTrue(snippet.startswith('<!-- dev-cycle: '))

        repo = 'acme/app'
        routes = {
            f'repos/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page=10': [
                {'number': 191, 'merged_at': '2026-11-25T17:30:00Z'},
                {'number': 190, 'merged_at': '2026-11-25T16:30:00Z'},
            ],
            f'repos/{repo}/pulls/191': {
                'number': 191, 'title': 'Clean PR </script>', 'state': 'closed',
                'created_at': '2026-11-25T17:15:00Z', 'merged_at': '2026-11-25T17:30:00Z',
                'head': {'sha': 'a' * 40}, 'body': 'Notes\n\n' + snippet,
            },
            f'repos/{repo}/pulls/191/commits': [{'sha': 'a' * 40, 'commit': {'committer': {'date': '2026-11-25T17:10:00Z'}}}],
            f'repos/{repo}/pulls/191/reviews': [{'state': 'APPROVED', 'submitted_at': '2026-11-25T17:28:00Z'}],
            f'repos/{repo}/pulls/191/files': [{'filename': 'src/core.py'}],
            f'repos/{repo}/issues/191/timeline': [{'event': 'ready_for_review', 'created_at': '2026-11-25T17:18:00Z'}],
            f'repos/{repo}/actions/runs?head_sha={"a" * 40}&per_page=50': {
                'workflow_runs': [
                    {'id': 502, 'name': 'checks', 'conclusion': 'skipped',
                     'created_at': '2026-11-25T17:15:05Z', 'updated_at': '2026-11-25T17:15:05Z'},
                    {'id': 501, 'name': 'checks', 'conclusion': 'success',
                     'created_at': '2026-11-25T17:18:05Z', 'updated_at': '2026-11-25T17:24:05Z'},
                ],
            },
            f'repos/{repo}/actions/runs/501/jobs?per_page=100': {
                'jobs': [{
                    'name': 'tests', 'conclusion': 'success',
                    'created_at': '2026-11-25T17:18:05Z', 'started_at': '2026-11-25T17:19:05Z',
                    'completed_at': '2026-11-25T17:24:05Z', 'steps': [],
                }],
            },
            f'repos/{repo}/pulls/190': {
                'number': 190, 'title': 'Retry PR', 'state': 'closed',
                'created_at': '2026-11-25T16:00:00Z', 'merged_at': '2026-11-25T16:30:00Z',
                'head': {'sha': 'b' * 40}, 'body': '',
            },
            f'repos/{repo}/pulls/190/commits': [{'sha': 'b' * 40, 'commit': {'committer': {'date': '2026-11-25T15:50:00Z'}}}],
            f'repos/{repo}/pulls/190/reviews': [],
            f'repos/{repo}/pulls/190/files': [{'filename': 'src/core.py'}],
            f'repos/{repo}/issues/190/timeline': [],
            f'repos/{repo}/actions/runs?head_sha={"b" * 40}&per_page=50': {
                'workflow_runs': [
                    {'id': 500, 'name': 'checks', 'conclusion': 'failure',
                     'created_at': '2026-11-25T16:01:00Z', 'updated_at': '2026-11-25T16:11:00Z'},
                ],
            },
            f'repos/{repo}/actions/runs/500/jobs?per_page=100': {
                'jobs': [{
                    'name': 'tests', 'conclusion': 'failure',
                    'created_at': '2026-11-25T16:01:00Z', 'started_at': '2026-11-25T16:03:00Z',
                    'completed_at': '2026-11-25T16:11:00Z', 'steps': [],
                }],
            },
        }
        fake_gh = make_fake_gh(self.base, routes)
        remote = self.base / 'state/remote.jsonl'
        col = self.run_cli('collect', '--apply', '--repo', repo, '--since', '2026-11-01',
                           '--limit', '10', '--gh', str(fake_gh), '--store', str(remote))
        self.assertEqual(col.returncode, 0, col.stderr)
        self.assertEqual(json.loads(col.stdout)['collected'], 2)

        single = json.loads(self.run_cli('analyze', '--store', str(remote), '--repo', repo, '--pr', '191').stdout)
        self.assertEqual(single['summary']['failed_spans'], 0)
        self.assertTrue(any(p['long_pole'] for p in single['phase_stats']))

        out_html = self.base / 'breakdown.html'
        ren = self.run_cli('render', '--apply', '--store', str(remote), '--repo', repo, '--output', str(out_html))
        self.assertEqual(ren.returncode, 0, ren.stderr)
        html_body = out_html.read_text(encoding='utf-8')
        self.assertIn('Phase Duration Breakdown', html_body)
        self.assertIn('long-pole', html_body)
        self.assertNotIn('Clean PR </script>', html_body)


if __name__ == '__main__':
    unittest.main()
