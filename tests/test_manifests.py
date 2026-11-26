"""Validate rstack marketplace manifests, plugin manifests, skill frontmatter, DAG hygiene, and generality."""

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / 'plugins/rstack'
SKILLS_DIR = PLUGIN_DIR / 'skills'

EXPECTED_SKILLS = {
    'state-machine-diagram',
    'state-requirements',
    'question-requirements',
    'delete-requirements',
    'auto-plan',
    'measure-dev-cycle',
    'scope-work',
    'status-report',
}

# Strict hierarchical DAG: child skills must stay agnostic to their callers.
FORBIDDEN_CALLER_REFS = {
    'state-machine-diagram': ('state-requirements', 'question-requirements', 'delete-requirements', 'auto-plan'),
    'measure-dev-cycle': ('scope-work', 'state-requirements', 'question-requirements', 'delete-requirements', 'auto-plan', 'status-report'),
    'scope-work': ('state-requirements', 'question-requirements', 'delete-requirements', 'auto-plan', 'status-report'),
    'state-requirements': ('question-requirements', 'delete-requirements', 'auto-plan'),
    'question-requirements': ('state-requirements', 'delete-requirements', 'auto-plan'),
    'delete-requirements': ('state-requirements', 'question-requirements', 'auto-plan'),
    'status-report': ('measure-dev-cycle', 'dev_cycle.py', 'question-requirements', 'delete-requirements', 'auto-plan'),
}


class ManifestAndDagTests(unittest.TestCase):
    def test_all_marketplace_manifests_resolve_to_plugin_directory(self):
        for rel in (
            '.claude-plugin/marketplace.json',
            '.cursor-plugin/marketplace.json',
            '.agents/plugins/marketplace.json',
        ):
            data = json.loads((ROOT / rel).read_text(encoding='utf-8'))
            self.assertEqual(data['name'], 'rstack', rel)
            plugins = data['plugins']
            self.assertEqual(len(plugins), 1, rel)
            entry = plugins[0]
            self.assertEqual(entry['name'], 'rstack', rel)
            source = entry['source']
            src_path = source['path'] if isinstance(source, dict) else source
            self.assertEqual((ROOT / src_path).resolve(), PLUGIN_DIR.resolve(), rel)

    def test_all_plugin_manifests_are_valid_and_cover_every_skill(self):
        actual_skills = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}
        self.assertEqual(actual_skills, EXPECTED_SKILLS)

        for rel in (
            'plugins/rstack/plugin.json',
            'plugins/rstack/.claude-plugin/plugin.json',
            'plugins/rstack/.cursor-plugin/plugin.json',
            'plugins/rstack/.codex-plugin/plugin.json',
        ):
            data = json.loads((ROOT / rel).read_text(encoding='utf-8'))
            self.assertEqual(data['name'], 'rstack', rel)
            self.assertEqual(data['license'], 'MIT', rel)

        claude = json.loads((PLUGIN_DIR / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))
        listed = {Path(s).name for s in claude['skills']}
        self.assertEqual(listed, EXPECTED_SKILLS)
        for rel_skill in claude['skills']:
            self.assertTrue((PLUGIN_DIR / rel_skill / 'SKILL.md').is_file(), rel_skill)

        cursor = json.loads((PLUGIN_DIR / '.cursor-plugin/plugin.json').read_text(encoding='utf-8'))
        self.assertTrue((PLUGIN_DIR / cursor['skills']).is_dir())
        self.assertTrue((PLUGIN_DIR / cursor['rules']).is_dir())

    def test_skill_frontmatter_and_hierarchical_dag_hygiene(self):
        for name in sorted(EXPECTED_SKILLS):
            body = (SKILLS_DIR / name / 'SKILL.md').read_text(encoding='utf-8')
            self.assertTrue(body.startswith(f'---\nname: {name}\ndescription:'), name)
            for forbidden in FORBIDDEN_CALLER_REFS.get(name, ()):
                self.assertNotIn(forbidden, body, f'child skill {name} must not reference caller/sibling {forbidden}')

    def test_rules_have_valid_frontmatter(self):
        rules = sorted((PLUGIN_DIR / 'rules').glob('*.mdc'))
        self.assertGreaterEqual(len(rules), 2)
        for rule in rules:
            text = rule.read_text(encoding='utf-8')
            self.assertTrue(text.startswith('---\ndescription:'), rule.name)
            self.assertIn('\nalwaysApply: true\n', text, rule.name)

    def test_repository_contains_no_project_specific_leaks(self):
        for path in sorted(ROOT.rglob('*')):
            if not path.is_file() or '.git' in path.parts or '__pycache__' in path.parts:
                continue
            if path == Path(__file__).resolve():
                continue
            text = path.read_text(encoding='utf-8', errors='ignore').lower()
            self.assertNotIn('holodesk', text, str(path.relative_to(ROOT)))


if __name__ == '__main__':
    unittest.main()
