"""Behavioral tests for the plan-implementer subagent (plan-implement-subagent).

The real plan-gate.sh, shell-write-gate.py and context-budget-gate.py are run with the
payload a spawned subagent sends (`agent_id`, `agent_type`). Fixtures are copied from
test_plan_gate_hooks.py and test_context_budget_gate.py on purpose (tests are not a package).
Tests 6 and 8 are STRUCTURAL guards: they prove the text exists, not that a model obeys it.
"""

import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
HOOKS = os.path.join(ROOT, '.claude', 'hooks')
RECORDER = os.path.join(ROOT, '.claude', 'operations', 'scripts', 'review-record.py')
CBG = os.path.join(HOOKS, 'context-budget-gate.py')
AGENT_FILE = os.path.join(ROOT, '.claude', 'agents', 'plan-implementer.md')
IMPLEMENT = os.path.join(ROOT, '.claude', 'commands', 'implement.md')
REFERENCE = os.path.join(ROOT, '.claude', 'agents', '_shared', 'implementer-reference.md')
PLAN = "# Plan: demo\n- **Files:** `app.py`\n- **Tier:** 3\n"
PROFILES = [None, 'minimal']


def _git(cwd, *a):
    return subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t', *a],
                          cwd=str(cwd), capture_output=True, text=True, check=True)


@pytest.fixture
def proj(tmp_path):
    """A git project with the kit's hooks + recorder copied in and a plans dir."""
    _git(tmp_path, 'init', '-q')
    _git(tmp_path, 'config', 'user.email', 't@t')
    _git(tmp_path, 'config', 'user.name', 't')
    (tmp_path / '.claude' / 'plans').mkdir(parents=True)
    (tmp_path / '.claude' / 'hooks').mkdir()
    (tmp_path / '.claude' / 'operations' / 'scripts').mkdir(parents=True)
    for name in ('lib.sh', 'plan-lib.sh', 'plan-gate.sh', 'checkpoint-gate.sh',
                 'shell-write-gate.py'):
        data = open(os.path.join(HOOKS, name)).read()
        dest = tmp_path / '.claude' / 'hooks' / name
        dest.write_text(data)
        dest.chmod(0o755)
    rec = tmp_path / '.claude' / 'operations' / 'scripts' / 'review-record.py'
    rec.write_text(open(RECORDER).read())
    (tmp_path / 'app.py').write_text('a = 1\nb = 2\n')
    _git(tmp_path, 'add', '.')
    _git(tmp_path, 'commit', '-qm', 'init')
    return tmp_path


def _hook(proj, name, payload, profile=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith('ECC_')}
    if profile:
        env['ECC_HOOK_PROFILE'] = profile
    path = str(proj / '.claude' / 'hooks' / name)
    cmd = [sys.executable, path] if name.endswith('.py') else ['bash', path]
    return subprocess.run(cmd, cwd=str(proj), input=json.dumps(payload), env=env,
                          capture_output=True, text=True, timeout=60)


def _approve(proj, files='`app.py`'):
    plan = proj / '.claude' / 'plans' / 'plan-demo.md'
    plan.write_text(PLAN.replace('`app.py`', files))
    subprocess.run([sys.executable, str(proj / '.claude/operations/scripts/review-record.py'),
                    'plan-write', str(plan), '--score', '95', '--decision', 'APPROVED',
                    '--owner-approved'], cwd=str(proj), check=True, capture_output=True)
    return plan


def _sub_edit(proj, path):
    # Write, not a one-line Edit: a single-line Edit of a Tier 3 file is a plan-gate carve-out.
    return {'tool_name': 'Write', 'agent_id': 'abc123', 'agent_type': 'plan-implementer',
            'tool_input': {'file_path': str(proj / path), 'content': 'x = 1\n'}}


def _bash(command, agent_type=None, **extra):
    payload = {'tool_name': 'Bash', 'tool_input': {'command': command}}
    if agent_type is not None:
        payload['agent_type'] = agent_type
    payload.update(extra)
    return payload


def usage_line(total):
    return json.dumps({"type": "assistant", "message": {"role": "assistant", "usage": {
        "input_tokens": total - 2, "cache_read_input_tokens": 1,
        "cache_creation_input_tokens": 1}}})


def _cbg(tmp_path, tool_name, extra_payload, parent):
    payload = {"session_id": "pytest-implsub", "tool_name": tool_name,
               "tool_input": {"file_path": "x.py"}, "transcript_path": str(parent)}
    payload.update(extra_payload)
    env = dict(os.environ)
    for key in ("CK_RAW_CONTEXT", "CK_ALLOW_GENERAL_PURPOSE", "CK_CONTEXT_WARN",
                "CK_CONTEXT_BLOCK", "CK_AGENT_BUDGET", "CK_ALLOW_MODEL_OVERRIDE"):
        env.pop(key, None)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    return subprocess.run([sys.executable, CBG], input=json.dumps(payload), capture_output=True,
                          text=True, env=env, cwd=str(tmp_path))


def _spawned(tmp_path, agent_id="abc123", meta_type=None):
    parent = tmp_path / "parent.jsonl"
    parent.write_text(usage_line(450000) + "\n")
    own = tmp_path / "parent" / "subagents"
    own.mkdir(parents=True, exist_ok=True)
    (own / ("agent-%s.jsonl" % agent_id)).write_text(usage_line(10000) + "\n")
    if meta_type is not None:
        (own / ("agent-%s.meta.json" % agent_id)).write_text(
            json.dumps({"agentType": meta_type, "model": "opus"}))
    return parent


def _frontmatter(path):
    text = open(path, encoding='utf-8').read()
    return text.split('---', 2)[1]


# 1
@pytest.mark.parametrize('profile', PROFILES)
def test_plan_gate_binds_a_subagent_payload(proj, profile):
    assert _hook(proj, 'plan-gate.sh', _sub_edit(proj, 'app.py'), profile).returncode == 2
    _approve(proj, '`app.py`')
    assert _hook(proj, 'plan-gate.sh', _sub_edit(proj, 'app.py'), profile).returncode == 0
    (proj / 'other.py').write_text('')
    assert _hook(proj, 'plan-gate.sh', _sub_edit(proj, 'other.py'), profile).returncode == 2


# 2
@pytest.mark.parametrize('profile', PROFILES)
def test_review_records_denied_to_a_subagent(proj, profile):
    _approve(proj, '`app.py`')
    res = _hook(proj, 'plan-gate.sh',
                _sub_edit(proj, '.claude/reports/reviews/x.json'), profile)
    assert res.returncode == 2


# 3
@pytest.mark.parametrize('profile', PROFILES)
def test_shell_write_gate_refuses_git_for_plan_implementer(proj, profile):
    res = _hook(proj, 'shell-write-gate.py', _bash('git commit -am x', 'plan-implementer'), profile)
    assert res.returncode == 2 and 'plan-implementer' in res.stderr
    for role in ('explore', None):
        assert _hook(proj, 'shell-write-gate.py', _bash('git commit -am x', role),
                     profile).returncode == 0
    assert _hook(proj, 'shell-write-gate.py',
                 _bash('python3 -m pytest tests/x -q', 'plan-implementer'),
                 profile).returncode == 0


# 4
def test_context_budget_gate_scopes_plan_implementer(tmp_path):
    agents = tmp_path / '.claude' / 'agents'
    agents.mkdir(parents=True)
    (agents / 'plan-implementer.md').write_text(open(AGENT_FILE, encoding='utf-8').read())
    (agents / 'explore.md').write_text(
        '---\nname: explore\ntools: ["Read", "Grep", "Glob"]\n---\n\nBody.\n')
    parent = _spawned(tmp_path)
    ok = _cbg(tmp_path, 'Edit', {'agent_id': 'abc123', 'agent_type': 'plan-implementer'}, parent)
    assert ok.returncode == 0, ok.stderr
    bad = _cbg(tmp_path, 'Edit', {'agent_id': 'abc123', 'agent_type': 'explore'}, parent)
    assert bad.returncode == 2, bad.stderr
    # fallback by meta file
    sub = tmp_path / 'm'
    sub.mkdir()
    meta_parent = _spawned(sub, meta_type='plan-implementer')
    via_meta = _cbg(tmp_path, 'Edit', {'agent_id': 'abc123'}, meta_parent)
    assert via_meta.returncode == 0, via_meta.stderr


# 5
def test_agent_file_contract():
    fm = _frontmatter(AGENT_FILE)
    tools = re.search(r'^tools:\s*(.*)$', fm, re.M).group(1)
    assert 'Edit' in tools and 'Write' in tools
    assert not re.search(r'^memory:', fm, re.M)
    assert int(re.search(r'^maxTurns:\s*(\d+)', fm, re.M).group(1)) <= 60
    registry = json.load(open(os.path.join(ROOT, '.claude', 'skills', 'skills-registry.json')))
    assert 'plan-implementer' in json.dumps(registry.get('agents', registry))
    assert 'implementer' in registry.get('removedAgents', {})
    assert not os.path.exists(os.path.join(ROOT, '.claude', 'agents', 'implementer.md'))


# 6 (structural guard)
def test_implement_command_documents_the_delegation():
    text = open(IMPLEMENT, encoding='utf-8').read()
    for needle in ('plan-implementer', '--inline', '--delegate',
                   '_shared/implementer-reference.md'):
        assert needle in text, needle
    assert 'Do not delegate edits' not in text
    ref = open(REFERENCE, encoding='utf-8').read()
    for heading in ('## Objective', '## Done when', '## Scope', '## Verify',
                    '## Stop and ask', '## Report', '## Original request'):
        assert re.search(r'^%s$' % re.escape(heading), ref, re.M), heading
    for needle in ('plan-check', 'status --porcelain --ignored', 'rev-parse HEAD',
                   'stash list', 'tag -l', 'rev-parse --show-toplevel'):
        assert needle in ref, needle


# 7
@pytest.mark.parametrize('meta_type,expected', [('plan-implementer', 2), ('explore', 0)])
def test_role_from_meta_file_fallback(proj, meta_type, expected):
    parent = _spawned(proj, meta_type=meta_type)
    payload = _bash('git status', None, agent_id='abc123', transcript_path=str(parent))
    assert _hook(proj, 'shell-write-gate.py', payload).returncode == expected


# 8 (structural guard)
def test_auto_delegate_rule_is_documented():
    ref = open(REFERENCE, encoding='utf-8').read()
    assert 'Delegate when files >= 3 OR steps >= 3, else inline' in ref
    for example in ('44 files, 11 steps', 'a 2-file 2-step plan -> inline',
                    'a 1-file 4-step plan -> delegate'):
        assert example in ref, example


GIT_TABLE = [
    ('git status', True), ('cd x && git status', True), ('/usr/bin/git log', True),
    ('env git status', True), ('$(git rev-parse HEAD)', True), ('GIT_DIR=x git log', True),
    ('xargs git rm', True), ('bash -c "git status"', True),
    ('ck lint --update-baseline', True), ('git commit --no-verify', True),
    ('echo "a; git status"', True),
    ('echo "git"', False), ('grep git f', False), ('pytest tests/test_git.py', False),
    ('gitleaks detect', False), ('python3 -m pytest tests/x -q', False),
]


# 9
@pytest.mark.parametrize('command,blocked', GIT_TABLE)
def test_git_forbidden_table(proj, command, blocked):
    res = _hook(proj, 'shell-write-gate.py', _bash(command, 'plan-implementer'))
    assert res.returncode == (2 if blocked else 0), (command, res.stderr)
    if command == 'xargs git rm':  # the existing T3-delete guard blocks it for every role
        return
    for role in ('explore', None):
        other = _hook(proj, 'shell-write-gate.py', _bash(command, role))
        assert other.returncode == 0, (command, role, other.stderr)
