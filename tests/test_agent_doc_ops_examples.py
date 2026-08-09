"""Every ops.json example embedded in the agent/skill corpus must validate clean.

Regression guard for AGENTS_KNOWN_ISSUES.md #9: `_shared/WORKFLOW_FILE_TEMPLATES.md` shipped
a legacy ops schema (`version` / `plan_ref` / `file` / `changes` /
`type: create|modify|delete|move|rename`) that `validate-config-json.py` rejects, so every
agent that followed the shared template produced a config the validator -- and therefore the
Reviewer -- had to reject. Prose review did not catch it for months; this test makes it
mechanical.

Behavioral, not structural: nothing is asserted about the markdown wording. Each embedded
example is materialized into a throwaway project (code_edit / file_delete targets created
with their find anchors, file_create targets deliberately absent) and the REAL validator is
executed against it. The example must be APPROVED (exit 0).
"""
import json
import os
import re
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
VALIDATOR = os.path.join(
    REPO_ROOT, '.claude', 'operations', 'scripts', 'validate-config-json.py'
)

# Corpus roots whose markdown teaches agents how to write ops.json.
DOC_ROOTS = (
    os.path.join('.claude', 'agents'),
    os.path.join('.claude', 'skills'),
)

# Docs that must keep at least this many ops examples. Without this floor, a fence-format or
# path change would make the scanner find nothing and the suite would stay green while the
# corpus kept teaching an unchecked schema.
MIN_EXAMPLES = {
    os.path.join('.claude', 'agents', '_shared', 'WORKFLOW_FILE_TEMPLATES.md'): 1,
    os.path.join('.claude', 'agents', 'planner.md'): 1,
    os.path.join('.claude', 'skills', 'generate-operations-config', 'SKILL.md'): 3,
}

# Keys from the rejected legacy schema. 'delete' is absent on purpose: it is a legal edit
# action ("delete": true).
LEGACY_KEYS = frozenset({
    'version', 'plan_ref', 'file', 'changes', 'action', 'target', 'dependencies',
    'rollback', 'validation', 'build_command', 'test_command', 'lint_command',
})
LEGACY_TYPES = frozenset({
    'create', 'modify', 'delete', 'move', 'rename',
    'create|modify|delete|move|rename',
})

# Substrings that mark a fence as ops-config-shaped even when it fails to parse.
OPS_MARKERS = ('"operations"', '"plan_ref"', 'file_create', 'file_delete', 'code_edit')

_FENCE_RE = re.compile(r'```json\n(.*?)```', re.S)


def _doc_files():
    for root in DOC_ROOTS:
        for dirpath, _dirs, names in os.walk(os.path.join(REPO_ROOT, root)):
            for name in names:
                if name.endswith('.md'):
                    yield os.path.relpath(os.path.join(dirpath, name), REPO_ROOT)


def _fences():
    for rel in sorted(_doc_files()):
        with open(os.path.join(REPO_ROOT, rel), encoding='utf-8') as handle:
            text = handle.read()
        for index, block in enumerate(_FENCE_RE.findall(text)):
            yield rel, index, block


def _is_ops_config(obj):
    """Deliberately does NOT key on 'plan': the bug under guard replaced 'plan' with
    'plan_ref', so a plan-keyed filter would skip exactly the broken example."""
    if not isinstance(obj, dict):
        return False
    if isinstance(obj.get('operations'), list) and obj['operations']:
        return True
    files = obj.get('files')
    return (isinstance(files, list) and bool(files)
            and all(isinstance(entry, dict) for entry in files))


def _collect():
    found = []
    for rel, index, block in _fences():
        try:
            parsed = json.loads(block)
        except ValueError:
            continue
        if _is_ops_config(parsed):
            found.append((rel, index, parsed))
    return found


OPS_EXAMPLES = _collect()


def _walk_keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _walk_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_keys(item)


def _materialize(config, root):
    """Build the on-disk state the example assumes: code_edit / file_delete targets exist
    (each find anchor present exactly once), file_create targets do not (GUARD 18)."""
    entries = list(config.get('operations', []))
    entries += [dict(entry, type='code_edit') for entry in config.get('files', [])]
    for operation in entries:
        path = operation.get('path')
        if not path or operation.get('type') == 'file_create':
            continue
        target = os.path.join(root, path)
        os.makedirs(os.path.dirname(target) or root, exist_ok=True)
        content = ''
        if os.path.exists(target):
            with open(target, encoding='utf-8') as handle:
                content = handle.read()
        for edit in operation.get('edits', []):
            anchor = edit.get('find')
            if anchor and anchor not in content:
                content += anchor + '\n'
        with open(target, 'w', encoding='utf-8') as handle:
            handle.write(content)


def _validate(config, root):
    with open(os.path.join(root, 'ops.json'), 'w', encoding='utf-8') as handle:
        json.dump(config, handle, indent=2)
    # Hook profile forced explicitly so the subprocess never inherits whatever profile the
    # developer session happens to run under (repo test convention).
    env = dict(os.environ, ECC_HOOK_PROFILE='minimal')
    return subprocess.run(
        [sys.executable, VALIDATOR, 'ops.json'],
        cwd=root, env=env, capture_output=True, text=True, timeout=120,
    )


@pytest.mark.parametrize(
    'rel,index,config', OPS_EXAMPLES,
    ids=['{}#{}'.format(rel, index) for rel, index, _config in OPS_EXAMPLES],
)
def test_embedded_ops_example_is_approved_by_the_validator(rel, index, config, tmp_path):
    root = str(tmp_path)
    _materialize(config, root)
    result = _validate(config, root)
    assert result.returncode == 0, (
        '{} (JSON block #{}) documents an ops config the validator REJECTS -- any agent '
        'copying it produces a config /validate-ops and the Reviewer must reject:\n{}{}'
        .format(rel, index, result.stdout, result.stderr)
    )


@pytest.mark.parametrize('rel,minimum', sorted(MIN_EXAMPLES.items()))
def test_documented_homes_still_carry_ops_examples(rel, minimum):
    count = sum(1 for found, _index, _config in OPS_EXAMPLES if found == rel)
    assert count >= minimum, (
        '{} exposes {} ops example(s), expected at least {} -- the scanner stopped seeing '
        'them (doc renamed, fence changed, or example dropped), which would silently '
        'disable this schema guard.'.format(rel, count, minimum)
    )


def test_ops_shaped_fences_are_parseable_json():
    broken = []
    for rel, index, block in _fences():
        try:
            json.loads(block)
        except ValueError as exc:
            if any(marker in block for marker in OPS_MARKERS):
                broken.append('{}#{}: {}'.format(rel, index, exc))
    assert not broken, (
        'ops-config-shaped JSON fence(s) do not parse, so the validator check above '
        'silently skips them:\n' + '\n'.join(broken)
    )


def test_ops_examples_use_no_legacy_schema_fields():
    offenders = []
    for rel, index, config in OPS_EXAMPLES:
        for key in _walk_keys(config):
            if key in LEGACY_KEYS:
                offenders.append('{}#{}: legacy key {!r}'.format(rel, index, key))
        for operation in config.get('operations', []):
            if isinstance(operation, dict) and operation.get('type') in LEGACY_TYPES:
                offenders.append('{}#{}: legacy operation type {!r}'.format(
                    rel, index, operation.get('type')))
    assert not offenders, (
        'AGENTS_KNOWN_ISSUES.md #9 regression -- the legacy ops schema is back in the agent '
        'corpus:\n' + '\n'.join(sorted(set(offenders)))
    )
