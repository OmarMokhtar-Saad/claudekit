"""Behavioral tests for scripts/check-context-floor.py — the always-on context
floor gate. Verifies (a) the repo currently passes its own budgets, (b) the
gate actually fails when a description grows past budget, and (c) agent
frontmatter descriptions stay free of <example> blocks (the 2026-08-17 strip
saved ~3.9k tokens per context window; this keeps it stripped).
"""
import json
import os
import re
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SCRIPT = os.path.join(REPO_ROOT, 'scripts', 'check-context-floor.py')
AGENTS_DIR = os.path.join(REPO_ROOT, '.claude', 'agents')

# Confusable pairs allowed to keep ONE routing example each.
EXAMPLE_ALLOWLIST = {'reviewer.md', 'code-reviewer.md', 'doc-updater.md', 'documenter.md'}


def run_gate(*args):
    return subprocess.run(
        [sys.executable, SCRIPT, *args], capture_output=True, text=True, cwd=REPO_ROOT
    )


def test_repo_within_budget():
    result = run_gate('--check')
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'TOTAL' in result.stdout


def test_gate_fails_when_over_budget(tmp_path):
    # Copy the script tree shape into a temp root with one oversized description.
    root = tmp_path
    (root / 'scripts').mkdir()
    (root / '.claude' / 'agents').mkdir(parents=True)
    (root / '.claude' / 'skills' / 'x').mkdir(parents=True)
    (root / '.claude' / 'commands').mkdir(parents=True)
    (root / 'CLAUDE.md').write_text('# minimal\n')
    big = 'x' * 20000
    (root / '.claude' / 'agents' / 'bloated.md').write_text(
        f'---\nname: bloated\ndescription: "{big}"\n---\nbody\n'
    )
    (root / '.claude' / 'skills' / 'x' / 'SKILL.md').write_text(
        '---\nname: x\ndescription: "small"\n---\nbody\n'
    )
    (root / '.claude' / 'commands' / 'c.md').write_text(
        '---\ndescription: "small"\n---\nbody\n'
    )
    with open(SCRIPT) as f:
        script_src = f.read()
    (root / 'scripts' / 'check-context-floor.py').write_text(script_src)
    result = subprocess.run(
        [sys.executable, str(root / 'scripts' / 'check-context-floor.py'), '--check'],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert 'OVER' in result.stdout
    assert 'over budget' in result.stderr

def test_json_output_shape():
    result = run_gate('--json')
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert set(payload) == {'sizes', 'budgets', 'total', 'ok'}
    assert set(payload['sizes']) == set(payload['budgets'])
    assert payload['total'] == sum(payload['sizes'].values())
    assert payload['ok'] is True, payload


def test_json_output_is_only_json():
    result = run_gate('--json')
    assert 'TOTAL' not in result.stdout
    assert 'OK:' not in result.stdout
    assert result.stderr == ''


def test_json_reports_not_ok_and_exits_1_when_over_budget(tmp_path):
    root = tmp_path
    (root / 'scripts').mkdir()
    (root / '.claude' / 'agents').mkdir(parents=True)
    (root / '.claude' / 'skills').mkdir(parents=True)
    (root / '.claude' / 'commands').mkdir(parents=True)
    (root / 'CLAUDE.md').write_text('tiny\n')
    (root / '.claude' / 'agents' / 'huge.md').write_text(
        '---\ndescription: "' + 'x' * 20000 + '"\n---\nbody\n'
    )
    with open(SCRIPT) as f:
        script_src = f.read()
    (root / 'scripts' / 'check-context-floor.py').write_text(script_src)
    result = subprocess.run(
        [sys.executable, str(root / 'scripts' / 'check-context-floor.py'), '--json', '--check'],
        capture_output=True, text=True,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload['ok'] is False
    assert payload['sizes']['agent descriptions'] > payload['budgets']['agent descriptions']


def test_claude_md_is_delivery_weighted():
    """CLAUDE.md is injected into the main context AND each of the 3 pipeline
    subagent spawns — the gate must measure delivered cost (chars x4), not
    file size, or moving content out of CLAUDE.md into a consuming agent
    would read as a regression."""
    result = run_gate('--json')
    assert result.returncode == 0, result.stdout + result.stderr
    import json as jsonlib
    payload = jsonlib.loads(result.stdout)
    file_chars = len(open(os.path.join(REPO_ROOT, 'CLAUDE.md')).read())
    assert payload['sizes']['CLAUDE.md'] == file_chars * 4


def test_gate_covers_pipeline_agent_bodies(tmp_path):
    """Review finding 2026-08-17: the per-spawn floor (planner/reviewer/
    implementer full bodies) grew 4% with nothing failing because only
    always-on categories were budgeted. This pins the new category."""
    root = tmp_path
    (root / 'scripts').mkdir()
    (root / '.claude' / 'agents').mkdir(parents=True)
    (root / '.claude' / 'skills' / 'x').mkdir(parents=True)
    (root / '.claude' / 'commands').mkdir(parents=True)
    (root / 'CLAUDE.md').write_text('# minimal\n')
    (root / '.claude' / 'skills' / 'x' / 'SKILL.md').write_text(
        '---\nname: x\ndescription: "small"\n---\nbody\n'
    )
    (root / '.claude' / 'commands' / 'c.md').write_text(
        '---\ndescription: "small"\n---\nbody\n'
    )
    (root / '.claude' / 'agents' / 'planner.md').write_text(
        '---\nname: planner\ndescription: "small"\n---\n' + 'x' * 50000
    )
    with open(SCRIPT) as f:
        (root / 'scripts' / 'check-context-floor.py').write_text(f.read())
    result = subprocess.run(
        [sys.executable, str(root / 'scripts' / 'check-context-floor.py'), '--check'],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert 'pipeline agent bodies' in result.stdout
    assert 'OVER' in result.stdout


@pytest.mark.parametrize(
    'agent_file',
    sorted(f for f in os.listdir(AGENTS_DIR) if f.endswith('.md') and not f[0].isupper()),
)
def test_agent_description_example_budget(agent_file):
    with open(os.path.join(AGENTS_DIR, agent_file)) as f:
        text = f.read()
    m = re.match(r'(?s)\A---\n(.*?)\n---\n', text)
    if not m:
        pytest.skip('no frontmatter')
    fm = m.group(1)
    count = len(re.findall(r'<example>', fm))
    allowed = 1 if agent_file in EXAMPLE_ALLOWLIST else 0
    assert count <= allowed, (
        f'{agent_file}: {count} <example> block(s) in frontmatter description '
        f'(allowed {allowed}). Examples in descriptions are injected into every '
        f'context window — keep routing in the first sentence instead.'
    )
