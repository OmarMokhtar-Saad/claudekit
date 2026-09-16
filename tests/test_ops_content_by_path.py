"""Behavioral tests: ops payloads referenced by path (`content_path` & friends).

Every test runs the real validator or executor as a subprocess inside a tmp_path
repo and asserts an exit code plus an on-disk outcome. The point of the feature is
that a referenced payload behaves EXACTLY like an inline one, and that the mandatory
`<key>_sha256` keeps the review-approval hash binding over bytes that live outside
ops.json.
"""

import hashlib
import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '.claude', 'operations', 'scripts')
)
VALIDATOR = os.path.join(SCRIPTS_DIR, 'validate-config-json.py')
EXECUTOR = os.path.join(SCRIPTS_DIR, 'execute-json-ops.py')

BODY = "line one\nline two\nline three\n"


def _env():
    env = os.environ.copy()
    env['ECC_HOOK_PROFILE'] = 'minimal'
    env.pop('CLAUDEKIT_EXTRA_PROTECTED', None)
    return env


def _run(script, cwd, *args):
    return subprocess.run([sys.executable, script] + [str(a) for a in args],
                          cwd=str(cwd), capture_output=True, text=True,
                          timeout=120, env=_env())


def _sha(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def _payload(tmp_path, text=BODY, name='body.txt'):
    rel = os.path.join('.claude', 'plans', 'payloads', 'demo', name)
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        target.write_bytes(text)
    else:
        target.write_text(text, encoding='utf-8')
    return rel, target


def _ops(tmp_path, operations, name='ops.json'):
    path = tmp_path / name
    path.write_text(json.dumps({'plan': 'payload-demo', 'operations': operations}),
                    encoding='utf-8')
    return path


def _create_by_path(rel, digest, path='out.txt'):
    return {'type': 'file_create', 'path': path,
            'content_path': rel, 'content_sha256': digest}


class TestValidatorAcceptsAReference:
    def test_a_correct_reference_validates(self, tmp_path):
        rel, _ = _payload(tmp_path)
        ops = _ops(tmp_path, [_create_by_path(rel, _sha(BODY))])
        res = _run(VALIDATOR, tmp_path, ops)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_an_inline_config_still_validates(self, tmp_path):
        ops = _ops(tmp_path, [{'type': 'file_create', 'path': 'out.txt', 'content': BODY}])
        res = _run(VALIDATOR, tmp_path, ops)
        assert res.returncode == 0, res.stdout + res.stderr


class TestValidatorRefusesUnsafeReferences:
    def test_missing_digest_is_refused(self, tmp_path):
        rel, _ = _payload(tmp_path)
        ops = _ops(tmp_path, [{'type': 'file_create', 'path': 'out.txt',
                               'content_path': rel}])
        assert _run(VALIDATOR, tmp_path, ops).returncode != 0

    def test_digest_mismatch_is_refused(self, tmp_path):
        """The approval-gate proof: ops.json is unchanged (so its approved hash still
        matches) but the payload on disk was rewritten -- this must not execute."""
        rel, target = _payload(tmp_path)
        ops = _ops(tmp_path, [_create_by_path(rel, _sha(BODY))])
        assert _run(VALIDATOR, tmp_path, ops).returncode == 0
        target.write_text("tampered\n", encoding='utf-8')
        res = _run(VALIDATOR, tmp_path, ops)
        assert res.returncode != 0
        assert 'digest mismatch' in res.stdout + res.stderr

    def test_inline_and_reference_together_are_refused(self, tmp_path):
        rel, _ = _payload(tmp_path)
        ops = _ops(tmp_path, [{'type': 'file_create', 'path': 'out.txt', 'content': BODY,
                               'content_path': rel, 'content_sha256': _sha(BODY)}])
        assert _run(VALIDATOR, tmp_path, ops).returncode != 0

    def test_traversal_outside_the_root_is_refused(self, tmp_path):
        outside = tmp_path.parent / 'outside.txt'
        outside.write_text(BODY, encoding='utf-8')
        ops = _ops(tmp_path, [_create_by_path('../outside.txt', _sha(BODY))])
        res = _run(VALIDATOR, tmp_path, ops)
        assert res.returncode != 0
        assert 'outside the project root' in res.stdout + res.stderr

    def test_absolute_payload_path_is_refused(self, tmp_path):
        outside = tmp_path.parent / 'abs.txt'
        outside.write_text(BODY, encoding='utf-8')
        ops = _ops(tmp_path, [_create_by_path(str(outside), _sha(BODY))])
        assert _run(VALIDATOR, tmp_path, ops).returncode != 0

    def test_symlink_escaping_the_root_is_refused(self, tmp_path):
        outside = tmp_path.parent / 'linked.txt'
        outside.write_text(BODY, encoding='utf-8')
        link = tmp_path / 'payload.txt'
        os.symlink(str(outside), str(link))
        ops = _ops(tmp_path, [_create_by_path('payload.txt', _sha(BODY))])
        res = _run(VALIDATOR, tmp_path, ops)
        assert res.returncode != 0
        assert 'outside the project root' in res.stdout + res.stderr

    def test_missing_payload_file_is_refused(self, tmp_path):
        ops = _ops(tmp_path, [_create_by_path('no/such/file.txt', _sha(BODY))])
        assert _run(VALIDATOR, tmp_path, ops).returncode != 0

    def test_a_directory_payload_is_refused(self, tmp_path):
        (tmp_path / 'adir').mkdir()
        ops = _ops(tmp_path, [_create_by_path('adir', _sha(BODY))])
        res = _run(VALIDATOR, tmp_path, ops)
        assert res.returncode != 0
        assert 'regular file' in res.stdout + res.stderr

    def test_non_utf8_payload_is_refused(self, tmp_path):
        raw = b'\xff\xfe\x00binary'
        rel, _ = _payload(tmp_path, raw, name='bin.dat')
        ops = _ops(tmp_path, [_create_by_path(rel, _sha(raw))])
        res = _run(VALIDATOR, tmp_path, ops)
        assert res.returncode != 0
        assert 'UTF-8' in res.stdout + res.stderr

    def test_legacy_format_refuses_references(self, tmp_path):
        rel, _ = _payload(tmp_path)
        (tmp_path / 'target.txt').write_text("alpha\n", encoding='utf-8')
        path = tmp_path / 'legacy.json'
        path.write_text(json.dumps({'plan': 'legacy-demo', 'files': [
            {'path': 'target.txt',
             'edits': [{'find': 'alpha', 'replace_path': rel,
                        'replace_sha256': _sha(BODY)}]}]}), encoding='utf-8')
        assert _run(VALIDATOR, tmp_path, path).returncode != 0


class TestReviewerNamedGaps:
    """Negative cases the plan claimed by construction; each is now measured."""

    def test_an_oversized_payload_is_refused(self, tmp_path):
        big = "x" * (2 * 1024 * 1024 + 1) + "\n"
        rel, _ = _payload(tmp_path, text=big)
        ops = _ops(tmp_path, [_create_by_path(rel, _sha(big))])
        res = _run(VALIDATOR, tmp_path, ops)
        assert res.returncode != 0
        assert not (tmp_path / 'out.txt').exists()

    def test_a_symlinked_parent_directory_escaping_the_root_is_refused(self, tmp_path):
        outside = tmp_path.parent / (tmp_path.name + '-outside')
        outside.mkdir(exist_ok=True)
        (outside / 'body.txt').write_text(BODY, encoding='utf-8')
        link_parent = tmp_path / '.claude' / 'plans' / 'payloads' / 'demo'
        link_parent.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(str(outside), str(link_parent))
        rel = os.path.join('.claude', 'plans', 'payloads', 'demo', 'body.txt')
        ops = _ops(tmp_path, [_create_by_path(rel, _sha(BODY))])
        assert _run(VALIDATOR, tmp_path, ops).returncode != 0
        res = _run(EXECUTOR, tmp_path, ops)
        assert res.returncode != 0
        assert not (tmp_path / 'out.txt').exists()

    def test_a_fifo_is_refused_without_blocking(self, tmp_path):
        rel = os.path.join('.claude', 'plans', 'payloads', 'demo', 'body.txt')
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        os.mkfifo(str(tmp_path / rel))
        ops = _ops(tmp_path, [_create_by_path(rel, _sha(BODY))])
        # a reader that opened the FIFO would hang forever; the 120 s timeout is the oracle
        assert _run(VALIDATOR, tmp_path, ops).returncode != 0

    def test_dry_run_still_refuses_a_tampered_digest(self, tmp_path):
        rel, payload = _payload(tmp_path)
        ops = _ops(tmp_path, [_create_by_path(rel, _sha(BODY))])
        payload.write_text("tampered\n", encoding='utf-8')
        res = _run(EXECUTOR, tmp_path, ops, '--dry-run')
        assert res.returncode != 0
        assert 'payload-ref-error' in res.stdout + res.stderr

    def test_after_projection_reports_a_payload_error_instead_of_swallowing_it(self, tmp_path):
        """Reviewer MAJOR: the --after projection must surface resolver errors."""
        rel, _ = _payload(tmp_path)
        bad = _ops(tmp_path, [{'type': 'file_create', 'path': 'out.txt',
                               'content_path': rel}])          # digest missing
        good_rel, _ = _payload(tmp_path, name='other.txt')
        good = _ops(tmp_path, [_create_by_path(good_rel, _sha(BODY))], name='good.json')
        res = _run(VALIDATOR, tmp_path, good, '--after', bad)
        assert '--after' in res.stdout + res.stderr
        assert 'content_sha256' in res.stdout + res.stderr


class TestExecutorAppliesAReference:
    def test_created_file_matches_the_payload_byte_for_byte(self, tmp_path):
        rel, payload = _payload(tmp_path)
        ops = _ops(tmp_path, [_create_by_path(rel, _sha(BODY))])
        res = _run(EXECUTOR, tmp_path, ops)
        assert res.returncode == 0, res.stdout + res.stderr
        assert (tmp_path / 'out.txt').read_bytes() == BODY.encode('utf-8')
        # Rollback needs the payload: the engine reads it and never removes it.
        assert payload.exists()

    def test_reference_and_inline_produce_identical_files(self, tmp_path):
        rel, _ = _payload(tmp_path)
        ops = _ops(tmp_path, [
            _create_by_path(rel, _sha(BODY), path='by_ref.txt'),
            {'type': 'file_create', 'path': 'inline.txt', 'content': BODY},
        ])
        assert _run(EXECUTOR, tmp_path, ops).returncode == 0
        assert (tmp_path / 'by_ref.txt').read_bytes() == (tmp_path / 'inline.txt').read_bytes()

    def test_edit_replace_path_applies(self, tmp_path):
        target = tmp_path / 'target.txt'
        target.write_text("head\nANCHOR\ntail\n", encoding='utf-8')
        rel, _ = _payload(tmp_path, "REPLACED", name='frag.txt')
        ops = _ops(tmp_path, [{'type': 'code_edit', 'path': 'target.txt', 'edits': [
            {'find': 'ANCHOR', 'replace_path': rel, 'replace_sha256': _sha("REPLACED")}]}])
        res = _run(EXECUTOR, tmp_path, ops)
        assert res.returncode == 0, res.stdout + res.stderr
        assert target.read_text(encoding='utf-8') == "head\nREPLACED\ntail\n"

    def test_executor_refuses_a_tampered_payload_and_writes_nothing(self, tmp_path):
        rel, payload = _payload(tmp_path)
        ops = _ops(tmp_path, [_create_by_path(rel, _sha(BODY))])
        payload.write_text("tampered\n", encoding='utf-8')
        res = _run(EXECUTOR, tmp_path, ops)
        assert res.returncode != 0
        assert not (tmp_path / 'out.txt').exists()
        assert 'payload-ref-error' in res.stdout + res.stderr

    def test_dry_run_reports_the_source_and_writes_nothing(self, tmp_path):
        rel, _ = _payload(tmp_path)
        ops = _ops(tmp_path, [_create_by_path(rel, _sha(BODY))])
        res = _run(EXECUTOR, tmp_path, ops, '--dry-run')
        assert res.returncode == 0, res.stdout + res.stderr
        assert rel in res.stdout
        assert str(len(BODY.encode('utf-8'))) in res.stdout
        assert not (tmp_path / 'out.txt').exists()


class TestResolverGuardsDirectly:
    """The Python resolver is the real enforcement: jsonschema is optional in a
    zero-dependency install, and when present it reports these as a generic
    "not valid under any of the given schemas". These assert the actual guard."""

    def _shared(self):
        if SCRIPTS_DIR not in sys.path:
            sys.path.insert(0, SCRIPTS_DIR)
        import shared
        return shared

    def test_a_reference_without_its_digest_is_refused(self, tmp_path):
        rel, _ = _payload(tmp_path)
        cfg = {'plan': 'p', 'operations': [
            {'type': 'file_create', 'path': 'out.txt', 'content_path': rel}]}
        errors = self._shared().resolve_payload_refs(cfg, root=str(tmp_path))
        assert any('content_sha256' in e for e in errors)
        # Fail closed: the inline key is never materialised on an error.
        assert 'content' not in cfg['operations'][0]

    def test_two_references_on_one_edit_are_refused(self, tmp_path):
        rel, _ = _payload(tmp_path)
        cfg = {'plan': 'p', 'operations': [{'type': 'code_edit', 'path': 't.txt', 'edits': [
            {'find': 'x', 'replace_path': rel, 'replace_sha256': _sha(BODY),
             'add_after_path': rel, 'add_after_sha256': _sha(BODY)}]}]}
        errors = self._shared().resolve_payload_refs(cfg, root=str(tmp_path))
        assert any('more than one payload reference' in e for e in errors)

    def test_resolution_is_byte_exact(self, tmp_path):
        rel, _ = _payload(tmp_path)
        cfg = {'plan': 'p', 'operations': [
            {'type': 'file_create', 'path': 'out.txt',
             'content_path': rel, 'content_sha256': _sha(BODY)}]}
        assert self._shared().resolve_payload_refs(cfg, root=str(tmp_path)) == []
        assert cfg['operations'][0]['content'] == BODY
